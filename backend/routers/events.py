from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any
from backend.models.base import get_db
from backend.models.user import User
from backend.models.event import Event
from backend.models.game import Game
from backend.services.auth import get_current_user

router = APIRouter(prefix="/events", tags=["events"])

class EventCreate(BaseModel):
    game_id: str
    event_type: str
    side: Optional[str] = "offense"
    clip_id: Optional[str] = None
    time_seconds: Optional[float] = None
    down: Optional[int] = None
    distance: Optional[int] = None
    field_position: Optional[str] = None
    hash_position: Optional[str] = None
    formation: Optional[str] = None
    play_type: Optional[str] = None
    defensive_front: Optional[str] = None
    coverage: Optional[str] = None
    blitz: Optional[str] = None
    result: Optional[str] = None
    yards_gained: Optional[int] = None
    personnel: Optional[str] = None
    motion: Optional[bool] = False
    player: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None

@router.get("")
async def list_events(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Event).where(Event.game_id == game_id, Event.organization_id == user.organization_id))
    events = result.scalars().all()
    return [{
        "id": str(e.id), "event_type": e.event_type, "side": e.side or "offense",
        "down": e.down, "distance": e.distance, "formation": e.formation, "play_type": e.play_type,
        "defensive_front": e.defensive_front, "coverage": e.coverage, "blitz": e.blitz,
        "result": e.result, "yards_gained": e.yards_gained, "personnel": e.personnel,
        "motion": e.motion, "time_seconds": e.time_seconds, "player": e.player, "extra_data": e.extra_data,
    } for e in events]

@router.post("")
async def create_event(body: EventCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    game = await db.execute(select(Game).where(Game.id == body.game_id, Game.organization_id == user.organization_id))
    if not game.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Game not found")
    event = Event(organization_id=user.organization_id, **body.dict())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {"id": str(event.id)}

@router.post("/bulk")
async def bulk_create_events(events: list[EventCreate], user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    objs = [Event(organization_id=user.organization_id, **e.dict()) for e in events]
    db.add_all(objs)
    await db.commit()
    return {"created": len(objs)}

class EventUpdate(BaseModel):
    side: Optional[str] = None
    down: Optional[int] = None
    distance: Optional[int] = None
    field_position: Optional[str] = None
    hash_position: Optional[str] = None
    formation: Optional[str] = None
    play_type: Optional[str] = None
    defensive_front: Optional[str] = None
    coverage: Optional[str] = None
    blitz: Optional[str] = None
    result: Optional[str] = None
    yards_gained: Optional[int] = None
    personnel: Optional[str] = None
    motion: Optional[bool] = None
    time_seconds: Optional[float] = None
    player: Optional[str] = None

@router.patch("/{event_id}")
async def update_event(event_id: str, body: EventUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Event).where(Event.id == event_id, Event.organization_id == user.organization_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Only apply fields the client actually sent.
    changes = body.dict(exclude_unset=True)
    for k, v in changes.items():
        setattr(event, k, v)
    await db.commit()
    await db.refresh(event)
    return {
        "id": str(event.id), "event_type": event.event_type, "side": event.side or "offense",
        "down": event.down, "distance": event.distance, "formation": event.formation, "play_type": event.play_type,
        "defensive_front": event.defensive_front, "coverage": event.coverage, "blitz": event.blitz,
        "result": event.result, "yards_gained": event.yards_gained, "personnel": event.personnel,
        "motion": event.motion, "time_seconds": event.time_seconds, "player": event.player, "extra_data": event.extra_data,
    }

@router.delete("/{event_id}")
async def delete_event(event_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Event).where(Event.id == event_id, Event.organization_id == user.organization_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()
    return {"ok": True}
