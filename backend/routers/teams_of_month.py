from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.teams_of_month import TeamSubmission, FeaturedTeam
from backend.services.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/teams-of-month", tags=["teams-of-month"])

class SubmissionCreate(BaseModel):
    submitter_name: str
    submitter_email: str
    team_name: str
    sport: str
    school_or_org: str
    level: Optional[str] = None
    achievement: str
    season: Optional[str] = None

@router.get("/featured")
async def get_featured():
    from backend.models.base import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(FeaturedTeam).order_by(FeaturedTeam.month_year.desc()).limit(6))
        featured = result.scalars().all()
        return [{"id": str(f.id), "month_year": f.month_year, "submission_id": str(f.submission_id)} for f in featured]

@router.post("/submit")
async def submit_team(body: SubmissionCreate, db: AsyncSession = Depends(get_db)):
    month_year = datetime.utcnow().strftime("%Y-%m")
    existing = await db.execute(select(TeamSubmission).where(TeamSubmission.submitter_email == body.submitter_email, TeamSubmission.month_year == month_year))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You've already submitted a team this month")
    sub = TeamSubmission(month_year=month_year, **body.dict())
    db.add(sub)
    await db.commit()
    return {"ok": True, "message": "Submission received!"}

@router.get("")
async def list_submissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TeamSubmission).order_by(TeamSubmission.created_at.desc()).limit(100))
    subs = result.scalars().all()
    return [{"id": str(s.id), "team_name": s.team_name, "sport": s.sport, "school_or_org": s.school_or_org, "achievement": s.achievement, "status": s.status, "month_year": s.month_year} for s in subs]
