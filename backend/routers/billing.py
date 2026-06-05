import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_MAP = {
    "coach": settings.STRIPE_PRICE_COACH,
    "athletic_dept": settings.STRIPE_PRICE_ATHLETIC_DEPT,
    "district": settings.STRIPE_PRICE_DISTRICT,
}

router = APIRouter(prefix="/billing", tags=["billing"])

class CheckoutRequest(BaseModel):
    tier: str
    success_url: str
    cancel_url: str

@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if body.tier not in PRICE_MAP:
        raise HTTPException(status_code=400, detail="Invalid tier")
    price_id = PRICE_MAP[body.tier]
    if not price_id:
        raise HTTPException(status_code=400, detail="Tier not configured")
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    et = event["type"]
    data = event["data"]["object"]

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
            await db.commit()

    elif et == "customer.subscription.updated":
        sub_id = data["id"]
        status = data["status"]
        await db.execute(update(Organization).where(Organization.stripe_subscription_id == sub_id).values(stripe_subscription_status=status))
        await db.commit()

    elif et == "customer.subscription.deleted":
        sub_id = data["id"]
        await db.execute(update(Organization).where(Organization.stripe_subscription_id == sub_id).values(
            stripe_subscription_status="canceled",
            subscription_tier="trial",
            is_trial=True,
        ))
        await db.commit()

    elif et == "invoice.payment_succeeded":
        customer_id = data.get("customer")
        if customer_id:
            sub = data.get("subscription")
            if sub:
                job = Job(job_type="referral_credit", payload={"customer_id": customer_id, "invoice_id": data["id"]})
                db.add(job)
                await db.commit()

    elif et == "invoice.payment_failed":
        customer_id = data.get("customer")
        if customer_id:
            result = await db.execute(select(Organization).where(Organization.stripe_customer_id == customer_id))
            org = result.scalar_one_or_none()
            if org:
                await db.execute(update(Organization).where(Organization.id == org.id).values(stripe_subscription_status="past_due"))
                await db.commit()

    return {"received": True}
