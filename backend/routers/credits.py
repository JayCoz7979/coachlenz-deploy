"""
Analysis-credit wallet + bundle purchase. Credits are separate from the subscription,
purchased in bundles, and never expire while the account is active. This is where a
coach checks the balance and buys more. Bundles use one-time Stripe Checkout with
inline price_data, so they need no pre-created Stripe products.
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
    """Wallet balance, the purchasable bundles, the per-analysis credit costs, and
    recent history. Credits never expire while the account is active."""
    bal = await credit_svc.balance(db, org.id)
    rows = (await db.execute(
        select(CreditLedger).where(CreditLedger.organization_id == org.id)
        .order_by(CreditLedger.created_at.desc()).limit(10)
    )).scalars().all()
    bundles = [{"id": k, "credits": c, "price_cents": p, "per_credit": round(p / 100 / c, 2)}
               for k, (c, p) in credit_svc.BUNDLES.items()]
    costs = {
        "standard": credit_svc.STANDARD_CREDITS,
        "deep_grade": credit_svc.DEEP_GRADE_CREDITS,
        "reanalysis": credit_svc.REANALYSIS_CREDITS,
    }
    return {"plan": plan_for(org), **bal, "bundles": bundles, "analysis_costs": costs,
            "history": [{"kind": r.kind, "amount": r.amount, "note": r.note,
                         "created_at": r.created_at.isoformat()} for r in rows]}


class BundleCheckout(BaseModel):
    bundle: str
    success_url: str
    cancel_url: str


@router.post("/checkout")
async def buy_bundle(body: BundleCheckout, request: Request,
                     user: User = Depends(get_current_user),
                     org: Organization = Depends(get_current_org),
                     db: AsyncSession = Depends(get_db)):
    if body.bundle not in credit_svc.BUNDLES:
        raise HTTPException(status_code=400, detail="Unknown credit bundle")
    n, price_cents = credit_svc.BUNDLES[body.bundle]

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
                "product_data": {"name": f"{n} CoachLenz analysis credits ({body.bundle.title()} bundle)"},
            },
        }],
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        metadata={"org_id": str(org.id), "kind": "credit_bundle", "credits": str(n)},
    )
    return {"checkout_url": session.url}
