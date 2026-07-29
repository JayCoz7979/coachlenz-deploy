from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.usage import AnalysisUsage, CoachUsageLimit
from backend.services.auth import get_current_user, get_current_org, hash_password, verify_password
from backend.services.trial import is_trial_active, get_trial_days_remaining
from backend.services.permissions import role_permissions
from backend.services.usage import month_start

router = APIRouter(prefix="/me", tags=["me"])

@router.get("")
async def get_me(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org)):
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        # Capabilities for this role, so the UI can show/hide actions (Track 5.1).
        "permissions": sorted(role_permissions(user.role)),
        "phone": user.phone,
        "phone_verified": user.phone_verified,
        "avatar_url": user.avatar_url,
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "subscription_tier": org.subscription_tier,
            "is_trial": org.is_trial,
            "trial_active": is_trial_active(org),
            "trial_days_remaining": get_trial_days_remaining(org),
            "has_coach_tenure_access": org.has_coach_tenure_access,
            "admin_level": org.admin_level,
        }
    }

@router.get("/usage")
async def my_usage(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """This coach's own analysis usage this month, and any AD-set cap."""
    ms = month_start(datetime.utcnow())
    cres = await db.execute(select(func.count()).select_from(AnalysisUsage).where(
        AnalysisUsage.user_id == user.id, AnalysisUsage.created_at >= ms))
    used = cres.scalar_one() or 0
    lres = await db.execute(select(CoachUsageLimit).where(
        CoachUsageLimit.organization_id == user.organization_id,
        CoachUsageLimit.user_id == user.id))
    row = lres.scalar_one_or_none()
    limit = row.monthly_run_limit if row and row.monthly_run_limit > 0 else None
    return {"runs_this_month": used, "monthly_limit": limit,
            "remaining": (None if not limit else max(0, limit - used))}


class UpdateMeRequest(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None

@router.patch("")
async def update_me(body: UpdateMeRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.execute(update(User).where(User.id == user.id).values(**updates))
        await db.commit()
    return {"ok": True}

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.execute(update(User).where(User.id == user.id).values(hashed_password=hash_password(body.new_password)))
    await db.commit()
    return {"ok": True}
