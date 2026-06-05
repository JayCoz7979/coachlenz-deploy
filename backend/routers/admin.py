from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.abuse import RiskFlag, AuditLog
from backend.models.teams_of_month import TeamSubmission, FeaturedTeam
from backend.services.auth import get_current_user, require_role
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(user: User = Depends(require_role("owner"))):
    if not user:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

@router.get("/orgs")
async def list_orgs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()).limit(200))
    orgs = result.scalars().all()
    return [{"id": str(o.id), "name": o.name, "slug": o.slug, "subscription_tier": o.subscription_tier, "is_trial": o.is_trial, "has_coach_tenure_access": o.has_coach_tenure_access, "created_at": o.created_at.isoformat()} for o in orgs]

class OrgUpdate(BaseModel):
    subscription_tier: Optional[str] = None
    is_trial: Optional[bool] = None
    has_coach_tenure_access: Optional[bool] = None
    admin_level: Optional[str] = None

@router.patch("/orgs/{org_id}")
async def update_org(org_id: str, body: OrgUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.execute(update(Organization).where(Organization.id == org_id).values(**updates))
        await db.commit()
    return {"ok": True}

@router.get("/risk-flags")
async def list_risk_flags(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RiskFlag).where(RiskFlag.resolved_at == None).order_by(RiskFlag.created_at.desc()).limit(100))
    flags = result.scalars().all()
    return [{"id": str(f.id), "flag_type": f.flag_type, "severity": f.severity, "details": f.details, "created_at": f.created_at.isoformat()} for f in flags]

@router.post("/submissions/{submission_id}/approve")
async def approve_submission(submission_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TeamSubmission).where(TeamSubmission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.status = "approved"
    sub.reviewed_by = user.id
    sub.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}

@router.post("/submissions/{submission_id}/feature")
async def feature_submission(submission_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TeamSubmission).where(TeamSubmission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    month_year = sub.month_year
    featured = FeaturedTeam(submission_id=sub.id, month_year=month_year)
    sub.status = "featured"
    sub.reviewed_by = user.id
    sub.reviewed_at = datetime.utcnow()
    db.add(featured)
    await db.commit()
    return {"ok": True}

@router.get("/stats")
async def platform_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from backend.models.game import Game
    from backend.models.report import TendencyReport
    orgs = await db.execute(select(func.count()).select_from(Organization))
    users = await db.execute(select(func.count()).select_from(User))
    games = await db.execute(select(func.count()).select_from(Game))
    reports = await db.execute(select(func.count()).select_from(TendencyReport))
    return {
        "total_orgs": orgs.scalar() or 0,
        "total_users": users.scalar() or 0,
        "total_games": games.scalar() or 0,
        "total_reports": reports.scalar() or 0,
    }
