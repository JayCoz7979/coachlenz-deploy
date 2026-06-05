import asyncio
import logging
import stripe
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.referral import Referral, ReferralSettings
from backend.models.organization import Organization
from backend.services.email_service import send_referral_credit_email
from backend.config import settings
from sqlalchemy import select, func, update

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

class ReferralsWorker(BaseWorker):
    job_type = "referral_credit"

    async def handle(self, payload: dict) -> dict:
        customer_id = payload.get("customer_id")
        if not customer_id:
            return {}

        async with AsyncSessionLocal() as db:
            org_result = await db.execute(select(Organization).where(Organization.stripe_customer_id == customer_id))
            org = org_result.scalar_one_or_none()
            if not org or not org.referred_by_org_id:
                return {}

            ref_result = await db.execute(select(Referral).where(
                Referral.referred_org_id == org.id,
                Referral.status == "converted",
            ))
            referral = ref_result.scalar_one_or_none()
            if not referral:
                ref_result2 = await db.execute(select(Referral).where(
                    Referral.referred_org_id == org.id,
                    Referral.status == "pending",
                ))
                referral = ref_result2.scalar_one_or_none()
            if not referral:
                return {}

            s_result = await db.execute(select(ReferralSettings))
            s = s_result.scalar_one()

            count_result = await db.execute(select(func.count()).where(
                Referral.referrer_org_id == org.referred_by_org_id,
                Referral.status.in_(["converted", "paid"]),
            ))
            paid_count = count_result.scalar() or 0

            if paid_count >= s.tier3_min_referrals:
                pct = float(s.tier3_pct)
                tier = 3
            elif paid_count >= s.tier2_min_referrals:
                pct = float(s.tier2_pct)
                tier = 2
            else:
                pct = float(s.tier1_pct)
                tier = 1

            referrer_result = await db.execute(select(Organization).where(Organization.id == org.referred_by_org_id))
            referrer = referrer_result.scalar_one_or_none()
            if not referrer or not referrer.stripe_customer_id:
                return {}

            invoice = stripe.Invoice.retrieve(payload.get("invoice_id", "")) if payload.get("invoice_id") else None
            amount = invoice.amount_paid if invoice else 0
            credit_cents = int(amount * pct / 100)

            if credit_cents > 0:
                stripe.Customer.create_balance_transaction(
                    referrer.stripe_customer_id,
                    amount=-credit_cents,
                    currency="usd",
                    description=f"CoachLenz referral commission {pct}%",
                )

            await db.execute(update(Referral).where(Referral.id == referral.id).values(
                status="paid",
                commission_tier=tier,
                commission_pct=pct,
                stripe_credit_cents=credit_cents,
            ))
            await db.commit()

            from backend.models.user import User
            owner = await db.execute(select(User).where(User.organization_id == referrer.id, User.role == "owner"))
            owner = owner.scalar_one_or_none()
            if owner and credit_cents > 0:
                try:
                    await send_referral_credit_email(owner.email, owner.name, f"${credit_cents / 100:.2f}")
                except Exception:
                    pass

        return {"credited_cents": credit_cents, "tier": tier}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ReferralsWorker().run_forever())
