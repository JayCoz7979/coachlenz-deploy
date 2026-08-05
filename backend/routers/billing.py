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
from backend.services.auth import get_current_user, get_current_org
from backend.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_MAP = {
    "coach": settings.STRIPE_PRICE_COACH,
    "athletic_dept": settings.STRIPE_PRICE_ATHLETIC_DEPT,
    "district": settings.STRIPE_PRICE_DISTRICT,
}

# Tiers with no self-serve Stripe price — they're sales-assisted. Kept out of
# PRICE_MAP on purpose; checkout returns a clear "contact sales" message instead of
# the bare "Invalid tier" (the UI already routes these to a Contact Sales CTA).
CONTACT_SALES_TIERS = {"enterprise"}

router = APIRouter(prefix="/billing", tags=["billing"])

class CheckoutRequest(BaseModel):
    tier: str
    success_url: str
    cancel_url: str

@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if body.tier in CONTACT_SALES_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"The {body.tier.title()} plan is sales-assisted — email info@cosbyaisolutions.com to get set up.",
        )
    if body.tier not in PRICE_MAP:
        raise HTTPException(status_code=400, detail="Invalid tier")
    price_id = PRICE_MAP[body.tier]
    if not price_id:
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
    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        metadata={"org_id": str(org.id), "tier": body.tier},
    )
    return {"checkout_url": session.url}

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
    }

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

    if et == "checkout.session.completed":
        org_id = data.get("metadata", {}).get("org_id")
        tier = data.get("metadata", {}).get("tier")
        if org_id and tier:
            await db.execute(update(Organization).where(Organization.id == org_id).values(
                subscription_tier=tier,
                is_trial=False,
                stripe_subscription_id=data.get("subscription"),
                stripe_subscription_status="active",
            ))

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

    elif et == "invoice.payment_succeeded":
        customer_id = data.get("customer")
        if customer_id:
            sub = data.get("subscription")
            if sub:
                job = Job(job_type="referral_credit", payload={"customer_id": customer_id, "invoice_id": data["id"]})
                db.add(job)

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
