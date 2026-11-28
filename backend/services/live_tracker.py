"""
$7 one-time Live Tracker entitlement (Live Game Logger + Halftime Sheet).

Product decision (Nov 28): everyone pays $7, including current users. There is no
grandfathering and no plan, trial, or admin bypass. An org can chart a live game
only after a completed, PAID Stripe Checkout for this offer has been confirmed by
the signed webhook (routers/billing.py). The check lives here, server-side, and
every /live route goes through it (routers/live_game.py):

  * write routes (start a game, log / edit / delete / flag a play, generate a
    report) refuse with 402 + a paywall payload when the org has not paid;
  * read routes (list games, open a game) stay readable so a coach's past games
    remain viewable, and they report ``access.live_tracker`` so the UI can show
    the paywall instead of the logging controls.

Reports already generated stay viewable through /reports (not gated here).
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.organization import Organization
from backend.services.auth import get_current_org

# Stripe Checkout metadata ``kind`` for this offer. The webhook grants access only
# for this kind, and only when the session reports payment_status == "paid".
LIVE_TRACKER_KIND = "live_tracker"

# Where the frontend sends a coach to buy. A path, so it works on any app host.
LIVE_TRACKER_PATH = "/live-tracker"

PAYWALL_CODE = "live_tracker_payment_required"
PAYWALL_MESSAGE = (
    "The Live Game Logger and Halftime Sheet are a $7 one-time purchase. "
    "Unlock it to start or keep logging games. Your past games and reports stay viewable."
)


def has_live_tracker_access(org: Optional[Organization]) -> bool:
    """True only once a paid $7 checkout has been recorded on the org."""
    return bool(org is not None and getattr(org, "live_tracker_purchased_at", None))


def paywall_detail() -> Dict[str, Any]:
    return {
        "code": PAYWALL_CODE,
        "message": PAYWALL_MESSAGE,
        "checkout_path": LIVE_TRACKER_PATH,
        "price_usd": 7,
    }


def assert_live_tracker_access(org: Optional[Organization]) -> None:
    """Raise 402 Payment Required with the paywall payload if the org has not paid."""
    if not has_live_tracker_access(org):
        raise HTTPException(status_code=402, detail=paywall_detail())


async def require_live_tracker(org: Organization = Depends(get_current_org)) -> Organization:
    """FastAPI dependency for every /live WRITE route."""
    assert_live_tracker_access(org)
    return org


def access_payload(org: Optional[Organization]) -> Dict[str, Any]:
    """Shape returned by the /live READ routes and GET /live/access."""
    paid = has_live_tracker_access(org)
    return {
        "live_tracker": paid,
        "checkout_path": LIVE_TRACKER_PATH,
        "price_usd": 7,
        **({} if paid else {"message": PAYWALL_MESSAGE, "code": PAYWALL_CODE}),
    }


def checkout_session_is_paid(session_obj: Dict[str, Any]) -> bool:
    """A Checkout Session grants access only when Stripe says it is actually paid.
    ``checkout.session.completed`` can arrive with payment_status 'unpaid' for delayed
    payment methods; those are granted later by checkout.session.async_payment_succeeded
    (which carries payment_status 'paid'), and a failure grants nothing."""
    return (session_obj or {}).get("payment_status") == "paid"


async def grant_live_tracker(db: AsyncSession, org_id: str, checkout_session_id: Optional[str]) -> None:
    """Record the purchase on the org. Idempotent: only the FIRST grant writes, so a
    redelivered or duplicate event can never move the timestamp or double-grant.
    (The webhook's ProcessedStripeEvent marker already dedupes by event id; this
    guard also covers two DIFFERENT events for the same purchase, e.g. completed +
    async_payment_succeeded.)"""
    await db.execute(
        update(Organization)
        .where(Organization.id == org_id, Organization.live_tracker_purchased_at.is_(None))
        .values(
            live_tracker_purchased_at=datetime.now(timezone.utc),
            live_tracker_checkout_session_id=checkout_session_id,
        )
    )
