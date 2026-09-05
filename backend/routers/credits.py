"""
Analysis-credit balance + top-up pack purchase. The plan grants monthly credits
(billing webhook); this is where a coach checks the balance and buys more when
depleted. Packs use one-time Stripe Checkout with inline price_data, so they need no
pre-created Stripe products.
"""
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.credits import CreditLedger
from backend.services.auth import get_current_user, get_current_org
from backend.services import credits as credit_svc
from backend.services.trial import plan_for
from backend.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("")
async def my_credits(user: User = Depends(get_current_user),
                     org: Organization = Depends(get_current_org),
                     db: AsyncSession = Depends(get_db)):
    """Balance, the plan's monthly grant, the buyable packs, and recent history."""
    bal = await credit_svc.balance(db, org.id)
    rows = (await db.execute(
        select(CreditLedger).where(CreditLedger.organization_id == org.id)
        .order_by(CreditLedger.created_at.desc()).limit(10)
    )).scalars().all()
    return {
        "plan": plan_for(org),
        "monthly_included": credit_svc.monthly_credits_for(org.subscription_tier),
        "credits_per_analysis": credit_svc.CREDITS_PER_ANALYSIS,
        **bal,
        "packs": [{"id": k, "credits": c, "price_cents": p} for k, (c, p) in credit_svc.PACKS.items()],
        "history": [{"kind": r.kind, "amount": r.amount, "note": r.note,
                     "created_at": r.created_at.isoformat()} for r in rows],
    }


class PackCheckout(BaseModel):
    pack: str
    success_url: str
    cancel_url: str


@router.post("/checkout")
async def buy_pack(body: PackCheckout, request: Request,
                   user: User = Depends(get_current_user),
                   org: Organization = Depends(get_current_org),
                   db: AsyncSession = Depends(get_db)):
    if body.pack not in credit_svc.PACKS:
        raise HTTPException(status_code=400, detail="Unknown credit pack")
    n, price_cents = credit_svc.PACKS[body.pack]

    customer_id = org.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=user.email, name=org.name, metadata={"org_id": str(org.id)})
        customer_id = customer.id
        await db.execute(update(Organization).where(Organization.id == org.id).values(stripe_customer_id=customer_id))
        await db.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": price_cents,
                "product_data": {"name": f"{n} CoachLenz analysis credits"},
            },
        }],
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        metadata={"org_id": str(org.id), "kind": "credit_pack", "credits": str(n)},
    )
    return {"checkout_url": session.url}
