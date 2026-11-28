import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.job import Job
from backend.models.billing_event import ProcessedStripeEvent
from backend.models.purchase_ip import PurchaseIPLog
from backend.services.auth import get_current_user, get_current_org
from backend.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

def refuse_live_key_outside_production() -> None:
    """503 before any Stripe call when a live key is configured outside production
    (Stage 2 QA L2). The app also refuses to start in that state (main.py)."""
    from backend.services.stripe_mode import live_key_outside_production
    if live_key_outside_production():
        raise HTTPException(
            status_code=503,
            detail="Checkout is disabled: this environment is not production and only "
                   "Stripe test mode is allowed. Nothing was charged.",
        )


# Monthly (default) price IDs, keyed by tier. Kept FLAT (tier -> price id) so the
# existing checkout + tier-coverage tests keep their contract.
PRICE_MAP = {
    "coach": settings.STRIPE_PRICE_COACH,
    "athletic_dept": settings.STRIPE_PRICE_ATHLETIC_DEPT,
    "district": settings.STRIPE_PRICE_DISTRICT,
}

# Annual (yearly-interval) price IDs, same keys. Empty until configured -> annual stays
# dormant (no toggle, annual checkout refused) and goes live the moment these are set.
ANNUAL_PRICE_MAP = {
    "coach": settings.STRIPE_PRICE_COACH_ANNUAL,
    "athletic_dept": settings.STRIPE_PRICE_ATHLETIC_DEPT_ANNUAL,
    "district": settings.STRIPE_PRICE_DISTRICT_ANNUAL,
}


def annual_available() -> bool:
    """True once the self-serve tiers have an annual price configured. Until then the
    annual toggle stays hidden and annual checkout is refused — so the wiring ships
    dormant and goes live the moment the annual price IDs are set in the env."""
    return bool(ANNUAL_PRICE_MAP["coach"] and ANNUAL_PRICE_MAP["athletic_dept"])

# Tiers with no self-serve Stripe price — they're sales-assisted. Kept out of
# PRICE_MAP on purpose; checkout returns a clear "contact sales" message instead of
# the bare "Invalid tier" (the UI already routes these to a Contact Sales CTA).
CONTACT_SALES_TIERS = {"enterprise"}

router = APIRouter(prefix="/billing", tags=["billing"])

class CheckoutRequest(BaseModel):
    tier: str
    success_url: str
    cancel_url: str
    # "monthly" (default) or "annual". Annual is refused until its price IDs are set.
    interval: str = "monthly"

@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, request: Request, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    refuse_live_key_outside_production()
    if body.tier in CONTACT_SALES_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"The {body.tier.title()} plan is sales-assisted — email info@cosbyaisolutions.com to get set up.",
        )
    if body.tier not in PRICE_MAP:
        raise HTTPException(status_code=400, detail="Invalid tier")
    interval = (body.interval or "monthly").strip().lower()
    if interval not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="Invalid billing interval")
    price_id = (ANNUAL_PRICE_MAP if interval == "annual" else PRICE_MAP).get(body.tier)
    if not price_id:
        if interval == "annual":
            raise HTTPException(
                status_code=400,
                detail="Annual billing isn't available yet — choose monthly, or email info@cosbyaisolutions.com.",
            )
        raise HTTPException(status_code=400, detail="Tier not configured")
    # Don't mint a SECOND subscription for an org that already has a live one. A
    # duplicate checkout orphans the first subscription (it keeps billing monthly,
    # but its customer.subscription.* webhooks no longer match this org because we
    # overwrite stripe_subscription_id with the newest), i.e. silent double-billing
    # the customer can't cancel cleanly. Route them to the portal to change/cancel.
    if org.stripe_subscription_status in ("active", "trialing", "past_due"):
        raise HTTPException(
            status_code=409,
            detail="You already have an active plan. Manage or change it from Billing.",
        )
    customer_id = org.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, name=org.name, metadata={"org_id": str(org.id)})
        customer_id = customer.id
        await db.execute(update(Organization).where(Organization.id == org.id).values(stripe_customer_id=customer_id))
        await db.commit()
    # Chargeback evidence: the IP + user agent of whoever initiated this purchase.
    # Pushed into Stripe metadata (session + subscription, so it shows in Stripe's
    # dispute view) AND logged in our DB (queryable per org during a dispute).
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        metadata={"org_id": str(org.id), "tier": body.tier, "interval": interval, "client_ip": ip or ""},
        subscription_data={"metadata": {"org_id": str(org.id), "interval": interval, "client_ip": ip or ""}},
    )
    db.add(PurchaseIPLog(
        organization_id=org.id, user_id=user.id, ip=ip, user_agent=(ua or "")[:400],
        tier=body.tier, stripe_session_id=session.id,
    ))
    await db.commit()
    return {"checkout_url": session.url}

# ── $7 one-time Live Tracker unlock ──────────────────────────────────────────
class LiveTrackerCheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str


def _allowed_redirect(url: str) -> bool:
    """Only send the buyer back to one of our own app origins (no open redirect)."""
    from urllib.parse import urlparse
    from backend.cors_config import build_allowed_origins

    try:
        parsed = urlparse(url or "")
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin in build_allowed_origins(settings.APP_URL, settings.ENVIRONMENT)


@router.post("/live-tracker/checkout")
async def live_tracker_checkout(body: LiveTrackerCheckoutRequest, request: Request,
                                user: User = Depends(get_current_user),
                                org: Organization = Depends(get_current_org),
                                db: AsyncSession = Depends(get_db)):
    """One-time $7 Checkout (mode=payment, quantity 1) for the Live Tracker.

    The price comes ONLY from STRIPE_PRICE_LIVE_TRACKER (a Stripe Price ID); nothing
    is inlined as price_data. Unset -> 503, fail closed. Access is granted by the
    webhook after Stripe reports the session paid, never by this endpoint or by the
    success redirect.
    """
    from backend.services.live_tracker import LIVE_TRACKER_KIND, has_live_tracker_access

    refuse_live_key_outside_production()
    price_id = (settings.STRIPE_PRICE_LIVE_TRACKER or "").strip()
    if not price_id or not (settings.STRIPE_SECRET_KEY or "").strip():
        raise HTTPException(
            status_code=503,
            detail="Live Tracker checkout isn't available yet. Nothing was charged. Please try again later.",
        )
    if has_live_tracker_access(org):
        raise HTTPException(status_code=409, detail="The Live Tracker is already unlocked for your account.")
    if not (_allowed_redirect(body.success_url) and _allowed_redirect(body.cancel_url)):
        raise HTTPException(status_code=400, detail="Invalid return URL")

    # One open Checkout Session per org (Stage 2 QA M1). Lock the org row so two tabs
    # (or a double click) serialize here, then reuse the session Stripe still reports
    # open instead of starting a second one that could also be paid. The lock is held
    # until the commit below, so nothing in this block may commit early.
    locked = (await db.execute(
        select(Organization).where(Organization.id == org.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one()
    if has_live_tracker_access(locked):
        await db.rollback()
        raise HTTPException(status_code=409, detail="The Live Tracker is already unlocked for your account.")

    reused = _open_live_tracker_session(locked)
    if reused is not None:
        await db.rollback()          # release the lock; nothing changed
        return {"checkout_url": reused.url, "reused": True}

    customer_id = locked.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, name=locked.name, metadata={"org_id": str(locked.id)})
        customer_id = customer.id

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    metadata = {"org_id": str(locked.id), "user_id": str(user.id), "kind": LIVE_TRACKER_KIND,
                "client_ip": ip or ""}
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        client_reference_id=str(locked.id),
        metadata=metadata,
        payment_intent_data={"metadata": metadata},
    )
    await db.execute(update(Organization).where(Organization.id == locked.id).values(
        stripe_customer_id=customer_id,
        live_tracker_open_session_id=session.id,
        live_tracker_open_session_expires_at=_stripe_ts(getattr(session, "expires_at", None)),
    ))
    db.add(PurchaseIPLog(
        organization_id=locked.id, user_id=user.id, ip=ip, user_agent=(ua or "")[:400],
        tier=LIVE_TRACKER_KIND, stripe_session_id=session.id,
    ))
    await db.commit()
    return {"checkout_url": session.url}


def _stripe_ts(value):
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _open_live_tracker_session(org: Organization):
    """The org's remembered $7 Checkout Session if Stripe still reports it open.

    A session Stripe reports complete/paid means the webhook has not landed yet:
    refuse (409) rather than let the coach start, and pay, a second session.
    Anything else (expired, unknown, Stripe error) falls through to a new session."""
    import logging
    from datetime import datetime, timezone

    sid = getattr(org, "live_tracker_open_session_id", None)
    if not sid:
        return None
    exp = getattr(org, "live_tracker_open_session_expires_at", None)
    if exp is not None:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            return None
    try:
        existing = stripe.checkout.Session.retrieve(sid)
    except Exception as e:      # network/API error: do not block checkout on it
        logging.getLogger(__name__).warning(
            "[live_tracker] could not retrieve open checkout session %s: %s", sid, type(e).__name__)
        return None
    status = getattr(existing, "status", None)
    if status == "open" and getattr(existing, "url", None):
        return existing
    if status == "complete" or getattr(existing, "payment_status", None) == "paid":
        raise HTTPException(
            status_code=409,
            detail="Your $7 payment is already being processed. The Live Tracker unlocks in a "
                   "moment. Refresh this page instead of paying again.",
        )
    return None


@router.post("/portal")
async def billing_portal(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org)):
    if not org.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found")
    session = stripe.billing_portal.Session.create(
        customer=org.stripe_customer_id,
        return_url=f"{settings.APP_URL}/settings/billing",
    )
    return {"portal_url": session.url}

@router.get("/status")
async def billing_status(org: Organization = Depends(get_current_org)):
    return {
        "tier": org.subscription_tier,
        "is_trial": org.is_trial,
        "stripe_status": org.stripe_subscription_status,
        "has_coach_tenure_access": org.has_coach_tenure_access,
        "billing_interval": org.billing_interval,
        # Lets the UI show the annual toggle only once annual price IDs are configured.
        "annual_available": annual_available(),
    }

@router.post("/allotment/run-monthly")
async def allotment_run_monthly(key: str = "", db: AsyncSession = Depends(get_db)):
    """Cron-driven monthly reset of the INCLUDED credit allotment for ANNUAL subscribers.

    Monthly subs get this reset from their monthly invoice (invoice.payment_succeeded).
    An annual sub's invoice fires only once a year, so without this their monthly
    included credits would refresh yearly instead of each month. Resets `included` only
    (purchased credits are never touched), idempotent per calendar month via an
    agent_logs marker so a re-run never double-resets. Guarded by RECAP_CRON_SECRET
    (?key=); dormant until that secret is set. Monthly subs are intentionally excluded
    here so their allotment is not reset twice a cycle."""
    import hmac
    from datetime import datetime as _dt
    from backend.services import credits as credit_svc
    from backend.models.agent_log import AgentLog

    if not (settings.RECAP_CRON_SECRET and key
            and hmac.compare_digest(key, settings.RECAP_CRON_SECRET)):
        raise HTTPException(status_code=403, detail="forbidden")

    cycle = _dt.utcnow().strftime("%Y-%m")
    cycle_marker = AgentLog.detail["cycle"].as_string()

    orgs = (await db.execute(select(Organization).where(
        Organization.subscription_tier.in_(["coach", "athletic_dept"]),
        Organization.stripe_subscription_status == "active",
        Organization.billing_interval == "annual",
    ))).scalars().all()

    reset, skipped = 0, 0
    for row in orgs:
        already = (await db.execute(select(AgentLog.id).where(
            AgentLog.organization_id == row.id,
            AgentLog.phase == "allotment_reset",
            cycle_marker == cycle,
        ).limit(1))).scalar_one_or_none()
        if already:
            skipped += 1
            continue
        await credit_svc.grant_monthly_allotment(db, row.id, row.subscription_tier)
        db.add(AgentLog(
            organization_id=row.id, agent_name="Billing", agent_role="billing",
            phase="allotment_reset", action=f"Annual included allotment reset for {cycle}",
            level="success", detail={"cycle": cycle, "tier": row.subscription_tier},
        ))
        await db.commit()
        reset += 1

    return {"cycle": cycle, "eligible_orgs": len(orgs), "reset": reset, "skipped": skipped}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None), db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        # Generic 400: don't echo Stripe's verification internals to the caller.
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    et = event["type"]
    data = event["data"]["object"]

    # Stage 2 QA L2: a test-mode environment never acts on a live-mode event (and
    # production never acts on a test-mode one). Acknowledged with 200 so Stripe does
    # not keep retrying, and NOT recorded as processed, so the event stays actionable
    # by the environment it belongs to.
    from backend.services.stripe_mode import event_livemode_mismatch
    if event_livemode_mismatch(event):
        import logging
        logging.getLogger(__name__).warning(
            "[billing] ignored Stripe event %s (%s): livemode does not match ENVIRONMENT", event.get("id"), et)
        return {"received": True, "ignored": "livemode_mismatch"}

    # Idempotency: Stripe delivers at-least-once and WILL redeliver events. Claim this
    # event id atomically by inserting its marker; if it's already recorded, this is a
    # redelivery — ack and skip so effects (subscription flips, referral credits) are
    # never applied twice. The marker is committed in the SAME transaction as the
    # effects below, so a mid-processing failure leaves the event UN-marked and Stripe
    # safely retries it.
    db.add(ProcessedStripeEvent(event_id=event["id"], event_type=et))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"received": True, "duplicate": True}

    if et in ("checkout.session.completed", "checkout.session.async_payment_succeeded") \
            and (data.get("metadata") or {}).get("kind") == "live_tracker":
        # $7 Live Tracker unlock. Grant ONLY when Stripe says the session is paid
        # (a delayed method completes as 'unpaid' and grants on async_payment_succeeded).
        # grant_live_tracker only writes while the grant is still NULL, so even a
        # distinct second event can't move it; the marker above stops redeliveries.
        from backend.services.live_tracker import (
            grant_live_tracker, live_tracker_session_is_paid, record_extra_payment,
        )
        if live_tracker_session_is_paid(data):
            org_id = data["metadata"]["org_id"]
            if not await grant_live_tracker(db, org_id, data.get("id")):
                # Already unlocked by another session: a second paid session is a
                # double charge. Flag it for a human refund (Stage 2 QA M1).
                await record_extra_payment(db, org_id, data)

    elif et == "checkout.session.completed":
        from backend.services import credits as credit_svc
        md = data.get("metadata", {})
        org_id = md.get("org_id")
        if md.get("kind") == "credit_bundle":
            # One-time credit bundle purchase. Credits never expire while active.
            n = int(md.get("credits") or 0)
            if org_id and n:
                await credit_svc.add_credits(db, org_id, n, ref=data.get("id"))
        else:
            tier = md.get("tier")
            if org_id and tier:
                # Subscription = cheap access. It grants NO purchased credits (those are
                # bought in bundles), but it DOES fund a monthly `included` allotment
                # (F1) so the base fee delivers credits every cycle. Store the Stripe
                # customer id too, so renewals (invoice.payment_succeeded) can find the
                # org to reset the allotment.
                interval = (md.get("interval") or "monthly").strip().lower()
                if interval not in ("monthly", "annual"):
                    interval = "monthly"
                await db.execute(update(Organization).where(Organization.id == org_id).values(
                    subscription_tier=tier,
                    is_trial=False,
                    billing_interval=interval,
                    stripe_subscription_id=data.get("subscription"),
                    stripe_subscription_status="active",
                    **({"stripe_customer_id": data.get("customer")} if data.get("customer") else {}),
                ))
                await credit_svc.grant_monthly_allotment(db, org_id, tier)

    elif et == "customer.subscription.updated":
        sub_id = data["id"]
        status = data["status"]
        await db.execute(update(Organization).where(Organization.stripe_subscription_id == sub_id).values(stripe_subscription_status=status))

    elif et == "customer.subscription.deleted":
        sub_id = data["id"]
        # A cancellation is NOT a trial. Setting is_trial=True regranted an
        # active, non-expiring trial to a churned customer (is_trial_active() is
        # True whenever is_trial is set and trial_ends_at is falsy), handing back
        # trial features and a fresh free-analysis slot. Downgrade to the free tier
        # with is_trial=False so they land in a plainly expired state.
        await db.execute(update(Organization).where(Organization.stripe_subscription_id == sub_id).values(
            stripe_subscription_status="canceled",
            subscription_tier="trial",
            is_trial=False,
        ))
        # Credits are forfeited on cancellation.
        from backend.services import credits as credit_svc
        res = await db.execute(select(Organization).where(Organization.stripe_subscription_id == sub_id))
        cancelled = res.scalar_one_or_none()
        if cancelled:
            await credit_svc.forfeit(db, cancelled.id)

    elif et == "invoice.payment_succeeded":
        customer_id = data.get("customer")
        if customer_id:
            sub = data.get("subscription")
            if sub:
                job = Job(job_type="referral_credit", payload={"customer_id": customer_id, "invoice_id": data["id"]})
                db.add(job)
                # Renewal: reset the monthly `included` allotment for the new cycle (F1).
                # No PURCHASED credits are granted here (those are bought in bundles).
                # grant_monthly_allotment SETs (not adds), so the first invoice right
                # after checkout is a harmless no-op.
                from backend.services import credits as credit_svc
                org_row = (await db.execute(select(Organization).where(
                    Organization.stripe_customer_id == customer_id))).scalar_one_or_none()
                if org_row:
                    await credit_svc.grant_monthly_allotment(db, org_row.id, org_row.subscription_tier)

    elif et == "invoice.payment_failed":
        customer_id = data.get("customer")
        if customer_id:
            result = await db.execute(select(Organization).where(Organization.stripe_customer_id == customer_id))
            org = result.scalar_one_or_none()
            if org:
                await db.execute(update(Organization).where(Organization.id == org.id).values(stripe_subscription_status="past_due"))

    # One commit: the idempotency marker + all effects persist atomically (or not at all).
    await db.commit()
    return {"received": True}
