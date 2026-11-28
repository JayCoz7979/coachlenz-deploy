"""
$7 one-time Live Tracker unlock: the Live Game Logger plus the Halftime Sheet.

The ONE place that decides whether an org may use the live logger, and the one
place that records a purchase. The /live routes call ``assert_live_tracker_access``
(server-side; the frontend paywall is only a convenience), and the Stripe webhook
calls ``grant_live_tracker`` after a PAID Checkout Session.

Who has access:
  1. An org that bought the $7 unlock (``live_tracker_purchased_at`` is set).
  2. An org with an ACTIVE paid subscription (``stripe_subscription_status ==
     'active'``). They already pay for the bigger product; a Stripe trial
     ('trialing'), past_due, canceled, or never-paid org does not count.
  3. Optional, OFF by default: orgs created before LIVE_TRACKER_GRANDFATHER_BEFORE
     (an ISO date). Empty = nobody is grandfathered.

Nothing else. Consent, verified email, and sport lock stay separate gates and are
never relaxed by this module.
"""
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import update

from backend.config import settings
from backend.models.organization import Organization

# Stripe Checkout Session metadata["kind"] for this offer. The webhook routes on it.
LIVE_TRACKER_KIND = "live_tracker"

# Coach-facing copy for the server-side refusal. The frontend shows it verbatim and
# links to /live-tracker. Keep it honest: $7 USD, one time.
LIVE_TRACKER_LOCKED_MESSAGE = (
    "The Live Tracker is a $7 one-time unlock. Unlock it at /live-tracker to chart "
    "games live and get the Halftime Sheet."
)

# Machine-readable reason, sent as a response header so the UI can route to the
# paywall without string-matching the message.
LOCKED_HEADER = {"X-CoachLenz-Locked": LIVE_TRACKER_KIND}


def _grandfather_cutoff() -> Optional[date]:
    raw = (settings.LIVE_TRACKER_GRANDFATHER_BEFORE or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        # A malformed value must not silently open the gate for everyone.
        return None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    if isinstance(value, date):
        return value
    return None


def has_live_tracker_access(org: Any) -> bool:
    if org is None:
        return False
    if getattr(org, "live_tracker_purchased_at", None):
        return True
    if (getattr(org, "stripe_subscription_status", None) or "").strip().lower() == "active":
        return True
    cutoff = _grandfather_cutoff()
    if cutoff is not None:
        created = _as_date(getattr(org, "created_at", None))
        if created is not None and created < cutoff:
            return True
    return False


def access_reason(org: Any) -> Optional[str]:
    """Why this org has access (for the UI and logs), or None when locked."""
    if org is None:
        return None
    if getattr(org, "live_tracker_purchased_at", None):
        return "purchased"
    if (getattr(org, "stripe_subscription_status", None) or "").strip().lower() == "active":
        return "subscription"
    if has_live_tracker_access(org):
        return "grandfathered"
    return None


def assert_live_tracker_access(org: Any) -> None:
    """403 unless the org has unlocked the Live Tracker. Server-side gate."""
    if not has_live_tracker_access(org):
        raise HTTPException(status_code=403, detail=LIVE_TRACKER_LOCKED_MESSAGE,
                            headers=LOCKED_HEADER)


async def grant_live_tracker(db, org_id: str, checkout_session_id: Optional[str]) -> None:
    """Record the purchase on the org. Idempotent: only writes while still NULL, so a
    redelivered event (or a second paid session) never moves the original grant.
    The caller commits (the webhook commits the idempotency marker in the same txn)."""
    await db.execute(
        update(Organization)
        .where(Organization.id == org_id, Organization.live_tracker_purchased_at.is_(None))
        .values(
            live_tracker_purchased_at=datetime.now(timezone.utc),
            live_tracker_checkout_session_id=checkout_session_id,
        )
    )


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
