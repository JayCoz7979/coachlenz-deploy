"""
$7 one-time Live Tracker unlock: the Live Game Logger plus the Halftime Sheet.

The ONE place that decides whether an org may use the live logger, and the one
place that records a purchase. The /live routes call ``assert_live_tracker_access``
(server-side; the frontend paywall is only a convenience), and the Stripe webhook
calls ``grant_live_tracker`` after a PAID Checkout Session.

Who has access (locked product decision, Nov 28 2026: "Everyone pays $7,
including current users"):
  Only an org that bought the $7 unlock (``live_tracker_purchased_at`` is set).
  No grandfathering by signup date, and an existing subscription does not count.

Unpaid orgs keep READ access to their past live games (GET /live/sessions,
GET /live/session/{id}) and their reports. Every write route refuses with 403
``live_tracker_payment_required``.

Nothing else. Consent, verified email, and sport lock stay separate gates and are
never relaxed by this module.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import update

from backend.config import settings
from backend.models.organization import Organization

logger = logging.getLogger(__name__)

# Stripe Checkout Session metadata["kind"] for this offer. The webhook routes on it.
LIVE_TRACKER_KIND = "live_tracker"

# Coach-facing copy for the server-side refusal. The frontend shows it verbatim and
# links to /live-tracker. Keep it honest: $7 USD, one time.
LIVE_TRACKER_LOCKED_MESSAGE = (
    "The Live Tracker is a $7 one-time unlock. Unlock it to chart games live and get "
    "the Halftime Sheet. Your past games and reports stay viewable."
)
# Machine-readable code in the 403 body, plus where the paywall lives.
LIVE_TRACKER_LOCKED_CODE = "live_tracker_payment_required"
LIVE_TRACKER_CHECKOUT_PATH = "/live-tracker"


def locked_detail() -> dict:
    """The 403 body detail: code + coach-facing message + checkout link."""
    return {
        "code": LIVE_TRACKER_LOCKED_CODE,
        "message": LIVE_TRACKER_LOCKED_MESSAGE,
        "checkout_url": LIVE_TRACKER_CHECKOUT_PATH,
        "price_usd": 7,
    }

# Machine-readable reason, sent as a response header so the UI can route to the
# paywall without string-matching the message.
LOCKED_HEADER = {"X-CoachLenz-Locked": LIVE_TRACKER_KIND}


def has_live_tracker_access(org: Any) -> bool:
    if org is None:
        return False
    return bool(getattr(org, "live_tracker_purchased_at", None))


def access_reason(org: Any) -> Optional[str]:
    """Why this org has access (for the UI and logs), or None when locked."""
    if org is None:
        return None
    return "purchased" if has_live_tracker_access(org) else None


def assert_live_tracker_access(org: Any) -> None:
    """403 unless the org has unlocked the Live Tracker. Server-side gate."""
    if not has_live_tracker_access(org):
        raise HTTPException(status_code=403, detail=locked_detail(), headers=LOCKED_HEADER)


async def grant_live_tracker(db, org_id: str, checkout_session_id: Optional[str]) -> bool:
    """Record the purchase on the org. Idempotent: only writes while still NULL, so a
    redelivered event (or a second paid session) never moves the original grant.
    Returns True only when this call made the grant. Also clears the remembered open
    Checkout Session (migration 068). The caller commits (the webhook commits the
    idempotency marker in the same txn)."""
    result = await db.execute(
        update(Organization)
        .where(Organization.id == org_id, Organization.live_tracker_purchased_at.is_(None))
        .values(
            live_tracker_purchased_at=datetime.now(timezone.utc),
            live_tracker_checkout_session_id=checkout_session_id,
            live_tracker_open_session_id=None,
            live_tracker_open_session_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    return (result.rowcount or 0) == 1


async def record_extra_payment(db, org_id: str, session_obj: dict) -> bool:
    """A PAID $7 session arrived for an org that already has the unlock (Stage 2 QA M1).

    If it is a DIFFERENT session from the one that made the grant, the coach paid
    twice: record it in live_tracker_extra_payments (needs_refund=true) and log a
    warning line for a human to refund in the Stripe dashboard. No automatic refund.
    Returns True when a new extra payment was recorded."""
    from sqlalchemy import select
    from backend.models.billing_event import LiveTrackerExtraPayment

    sid = session_obj.get("id")
    if not sid:
        return False
    granted_sid = (await db.execute(
        select(Organization.live_tracker_checkout_session_id).where(Organization.id == org_id)
    )).first()
    if granted_sid is None or granted_sid[0] == sid:
        return False        # unknown org, or a second event for the granting session
    exists = (await db.execute(
        select(LiveTrackerExtraPayment.checkout_session_id)
        .where(LiveTrackerExtraPayment.checkout_session_id == sid)
    )).first()
    if exists:
        return False
    pi = session_obj.get("payment_intent")
    if isinstance(pi, dict):
        pi = pi.get("id")
    db.add(LiveTrackerExtraPayment(
        checkout_session_id=sid,
        organization_id=uuid.UUID(str(org_id)),
        payment_intent_id=pi,
        amount_total=session_obj.get("amount_total"),
        currency=session_obj.get("currency"),
        needs_refund=True,
    ))
    logger.warning(
        "[live_tracker] extra paid checkout session %s for org %s, which already has the "
        "unlock from %s. Flagged needs_refund in live_tracker_extra_payments; refund by hand.",
        sid, org_id, granted_sid[0],
    )
    return True


def live_tracker_session_is_paid(session_obj: dict) -> bool:
    """True only for a Checkout Session Stripe reports as paid for THIS offer.

    checkout.session.completed also fires for delayed payment methods with
    payment_status='unpaid'; those grant nothing until
    checkout.session.async_payment_succeeded arrives.
    """
    md = session_obj.get("metadata") or {}
    return (
        md.get("kind") == LIVE_TRACKER_KIND
        and bool(md.get("org_id"))
        and session_obj.get("mode") == "payment"
        and session_obj.get("payment_status") == "paid"
    )
