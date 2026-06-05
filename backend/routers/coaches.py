from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.coach import CoachProfile, CoachMove
from backend.services.auth import get_current_user, get_current_org, require_coach_tenure

router = APIRouter(prefix="/coaches", tags=["coaches"])

class CoachCreate(BaseModel):
    name: str
    sport: Optional[str] = None
    position: Optional[str] = None
    bio: Optional[str] = None

class MoveCreate(BaseModel):
    school_name: str
    role: Optional[str] = None
    sport: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    wins: Optional[int] = None
    losses: Optional[int] = None
    notes: Optional[str] = None

@router.get("")
async def list_coaches(user: User = Depends(get_current_user), org: Organization = Depends(require_coach_tenure), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CoachProfile).where(CoachProfile.organization_id == user.organization_id, CoachProfile.is_active == True))
    coaches = result.scalars().all()
    return [{"id": str(c.id), "name": c.name, "sport": c.sport, "position": c.position} for c in coaches]

@router.post("")
async def create_coach(body: CoachCreate, user: User = Depends(get_current_user), org: Organization = Depends(require_coach_tenure), db: AsyncSession = Depends(get_db)):
    coach = CoachProfile(organization_id=user.organization_id, **body.dict())
    db.add(coach)
    await db.commit()
    await db.refresh(coach)
    return {"id": str(coach.id), "name": coach.name}

@router.get("/{coach_id}")
async def get_coach(coach_id: str, user: User = Depends(get_current_user), org: Organization = Depends(require_coach_tenure), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CoachProfile).where(CoachProfile.id == coach_id, CoachProfile.organization_id == user.organization_id))
    coach = result.scalar_one_or_none()
    if not coach:
        raise HTTPException(status_code=404, detail="Coach not found")
    moves_result = await db.execute(select(CoachMove).where(CoachMove.coach_id == coach.id).order_by(CoachMove.start_date.desc()))
    moves = moves_result.scalars().all()
    return {
        "id": str(coach.id),
        "name": coach.name,
        "sport": coach.sport,
        "position": coach.position,
        "bio": coach.bio,
        "photo_url": coach.photo_url,
        "moves": [{"id": str(m.id), "school_name": m.school_name, "role": m.role, "sport": m.sport, "start_date": str(m.start_date) if m.start_date else None, "end_date": str(m.end_date) if m.end_date else None, "is_current": m.is_current, "wins": m.wins, "losses": m.losses} for m in moves],
    }

@router.post("/{coach_id}/moves")
async def add_move(coach_id: str, body: MoveCreate, user: User = Depends(get_current_user), org: Organization = Depends(require_coach_tenure), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CoachProfile).where(CoachProfile.id == coach_id, CoachProfile.organization_id == user.organization_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Coach not found")
    move = CoachMove(coach_id=coach_id, organization_id=user.organization_id, **body.dict())
    db.add(move)
    await db.commit()
    return {"ok": True}
