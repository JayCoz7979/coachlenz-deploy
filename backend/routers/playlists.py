from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from backend.models.base import get_db
from backend.models.user import User
from backend.models.comms import Playlist, PlaylistClip
from backend.services.auth import get_current_user

router = APIRouter(prefix="/playlists", tags=["playlists"])

class PlaylistCreate(BaseModel):
    title: str
    description: Optional[str] = None
    is_shared: bool = False

class PlaylistClipAdd(BaseModel):
    clip_id: str
    position: int = 0
    note: Optional[str] = None

@router.get("")
async def list_playlists(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).where(Playlist.organization_id == user.organization_id).order_by(Playlist.created_at.desc()))
    playlists = result.scalars().all()
    return [{"id": str(p.id), "title": p.title, "is_shared": p.is_shared} for p in playlists]

@router.post("")
async def create_playlist(body: PlaylistCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    pl = Playlist(organization_id=user.organization_id, created_by=user.id, **body.dict())
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return {"id": str(pl.id), "title": pl.title}

@router.post("/{playlist_id}/clips")
async def add_clip(playlist_id: str, body: PlaylistClipAdd, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.organization_id == user.organization_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Playlist not found")
    pc = PlaylistClip(playlist_id=playlist_id, **body.dict())
    db.add(pc)
    await db.commit()
    return {"ok": True}

@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.organization_id == user.organization_id))
    pl = result.scalar_one_or_none()
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    await db.delete(pl)
    await db.commit()
    return {"ok": True}
