from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
import uuid
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.services.trial import can_upload_game, is_trial_active
from backend.services.r2 import generate_presigned_upload_url

router = APIRouter(prefix="/games", tags=["games"])

class GameCreate(BaseModel):
    title: str
    sport: str
    team_id: Optional[str] = None
    opponent: Optional[str] = None
    game_date: Optional[str] = None
    is_home: Optional[bool] = None
    file_name: str
    file_size_bytes: Optional[int] = None

@router.get("")
async def list_games(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).where(Game.organization_id == user.organization_id).order_by(Game.created_at.desc()))
    games = result.scalars().all()
    return [{"id": str(g.id), "title": g.title, "sport": g.sport, "opponent": g.opponent, "status": g.status, "game_date": str(g.game_date) if g.game_date else None, "is_trial_game": g.is_trial_game, "created_at": g.created_at.isoformat()} for g in games]

@router.post("")
async def create_game(body: GameCreate, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if not can_upload_game(org):
        raise HTTPException(status_code=403, detail="Trial game limit reached. Upgrade to upload more games.")
    key = f"games/{org.id}/{uuid.uuid4()}/{body.file_name}"
    presigned = generate_presigned_upload_url(key, "video/mp4")
    game = Game(
        organization_id=org.id,
        team_id=body.team_id,
        title=body.title,
        sport=body.sport,
        opponent=body.opponent,
        is_home=body.is_home,
        r2_key=key,
        file_size_bytes=body.file_size_bytes,
        status="pending",
        is_trial_game=is_trial_active(org),
    )
    db.add(game)
    await db.flush()
    job = Job(organization_id=org.id, job_type="ingest", payload={"game_id": str(game.id)})
    db.add(job)
    if is_trial_active(org):
        await db.execute(update(Organization).where(Organization.id == org.id).values(trial_games_used=Organization.trial_games_used + 1))
    await db.commit()
    return {"id": str(game.id), "upload_url": presigned["upload_url"], "key": key}

@router.get("/{game_id}")
async def get_game(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    from backend.services.r2 import generate_presigned_download_url
    download_url = generate_presigned_download_url(game.r2_key) if game.r2_key and game.status == "ready" else None
    return {"id": str(game.id), "title": game.title, "sport": game.sport, "opponent": game.opponent, "status": game.status, "download_url": download_url, "duration_seconds": game.duration_seconds, "is_trial_game": game.is_trial_game}

@router.delete("/{game_id}")
async def delete_game(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.r2_key:
        from backend.services.r2 import delete_object
        try:
            delete_object(game.r2_key)
        except Exception:
            pass
    await db.delete(game)
    await db.commit()
    return {"ok": True}
