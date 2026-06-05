from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.team import Team
from backend.services.auth import get_current_user

router = APIRouter(prefix="/teams", tags=["teams"])

class TeamCreate(BaseModel):
    name: str
    sport: str
    level: Optional[str] = None
    season: Optional[str] = None

@router.get("")
async def list_teams(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.organization_id == user.organization_id, Team.is_active == True))
    teams = result.scalars().all()
    return [{"id": str(t.id), "name": t.name, "sport": t.sport, "level": t.level, "season": t.season} for t in teams]

@router.post("")
async def create_team(body: TeamCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team = Team(organization_id=user.organization_id, **body.dict())
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return {"id": str(team.id), "name": team.name, "sport": team.sport}

@router.get("/{team_id}")
async def get_team(team_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.id == team_id, Team.organization_id == user.organization_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"id": str(team.id), "name": team.name, "sport": team.sport, "level": team.level, "season": team.season}

@router.delete("/{team_id}")
async def delete_team(team_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.id == team_id, Team.organization_id == user.organization_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.is_active = False
    await db.commit()
    return {"ok": True}
