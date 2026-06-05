from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import secrets
import string
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.referral import ReferralCode, Referral, ReferralSettings
from backend.services.auth import get_current_user, get_current_org
from backend.config import settings

router = APIRouter(prefix="/referrals", tags=["referrals"])

def _gen_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

@router.get("/code")
async def get_my_referral_code(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReferralCode).where(ReferralCode.organization_id == org.id, ReferralCode.is_active == True))
    code = result.scalar_one_or_none()
    if not code:
        code = ReferralCode(organization_id=org.id, code=_gen_code())
        db.add(code)
        await db.commit()
        await db.refresh(code)
    return {"code": code.code, "link": f"{settings.APP_URL}/refer/{code.code}"}

@router.get("/stats")
async def referral_stats(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    total = await db.execute(select(func.count()).where(Referral.referrer_org_id == org.id))
    converted = await db.execute(select(func.count()).where(Referral.referrer_org_id == org.id, Referral.status.in_(["converted", "paid"])))
    paid = await db.execute(select(func.count()).where(Referral.referrer_org_id == org.id, Referral.status == "paid"))
    settings_row = await db.execute(select(ReferralSettings))
    s = settings_row.scalar_one_or_none()
    return {
        "total_referrals": total.scalar() or 0,
        "converted": converted.scalar() or 0,
        "paid": paid.scalar() or 0,
        "current_tier_pct": float(s.tier1_pct) if s else 10.0,
    }

@router.get("/history")
async def referral_history(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Referral).where(Referral.referrer_org_id == org.id).order_by(Referral.created_at.desc()))
    refs = result.scalars().all()
    return [{"id": str(r.id), "status": r.status, "commission_pct": float(r.commission_pct), "stripe_credit_cents": r.stripe_credit_cents, "created_at": r.created_at.isoformat()} for r in refs]
