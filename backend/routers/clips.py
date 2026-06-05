from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.clip import Clip
from backend.models.game import Game
from backend.services.auth import get_current_user
from backend.services.r2 import generate_presigned_download_url

router = APIRouter(prefix="/clips", tags=["clips"])

class ClipCreate(BaseModel):
    game_id: str
    title: Optional[str] = None
    start_time: float
    end_time: float

@router.get("")
async def list_clips(game_id: Optional[str] = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Clip).where(Clip.organization_id == user.organization_id)
    if game_id:
        query = query.where(Clip.game_id == game_id)
    result = await db.execute(query.order_by(Clip.created_at.desc()))
    clips = result.scalars().all()
    return [{"id": str(c.id), "game_id": str(c.game_id), "title": c.title, "start_time": c.start_time, "end_time": c.end_time, "r2_url": c.r2_url} for c in clips]

@router.post("")
async def create_clip(body: ClipCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    game = await db.execute(select(Game).where(Game.id == body.game_id, Game.organization_id == user.organization_id))
    if not game.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Game not found")
    clip = Clip(organization_id=user.organization_id, created_by=user.id, **body.dict())
    db.add(clip)
    await db.commit()
    await db.refresh(clip)
    return {"id": str(clip.id), "start_time": clip.start_time, "end_time": clip.end_time}

@router.get("/{clip_id}")
async def get_clip(clip_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Clip).where(Clip.id == clip_id, Clip.organization_id == user.organization_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    url = generate_presigned_download_url(clip.r2_key) if clip.r2_key else None
    return {"id": str(clip.id), "title": clip.title, "start_time": clip.start_time, "end_time": clip.end_time, "download_url": url}

@router.delete("/{clip_id}")
async def delete_clip(clip_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Clip).where(Clip.id == clip_id, Clip.organization_id == user.organization_id))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    await db.delete(clip)
    await db.commit()
    return {"ok": True}
