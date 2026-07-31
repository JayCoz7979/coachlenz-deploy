from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any
from backend.models.base import get_db
from backend.models.user import User
from backend.models.event import Event
from backend.models.game import Game
from backend.models.organization import Organization
from backend.services.auth import get_current_user
from backend.services import learning_loop
from backend.services.learning_loop import CORRECTABLE_LABEL_FIELDS, EXTRA_DATA_LABEL_FIELDS

router = APIRouter(prefix="/events", tags=["events"])


def _event_out(e: Event) -> dict:
    return {
        "id": str(e.id), "event_type": e.event_type, "side": e.side or "offense",
        "down": e.down, "distance": e.distance, "formation": e.formation, "play_type": e.play_type,
        "defensive_front": e.defensive_front, "coverage": e.coverage, "blitz": e.blitz,
        "result": e.result, "yards_gained": e.yards_gained, "personnel": e.personnel,
        "motion": e.motion, "time_seconds": e.time_seconds, "player": e.player,
        "is_highlight": bool(e.is_highlight), "coach_note": e.coach_note, "extra_data": e.extra_data,
    }

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
    return [_event_out(e) for e in events]

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
    # Film-room coach marks.
    is_highlight: Optional[bool] = None
    coach_note: Optional[str] = None
    # Basketball (and other extra) fields live in extra_data — MERGED, not replaced,
    # so editing one scheme field never wipes the rest of the play's data.
    extra_data: Optional[Dict[str, Any]] = None

@router.patch("/{event_id}")
async def update_event(event_id: str, body: EventUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Event).where(Event.id == event_id, Event.organization_id == user.organization_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Only apply fields the client actually sent.
    changes = body.dict(exclude_unset=True)
    new_extra = changes.pop("extra_data", None)

    # §14 learning loop: snapshot the LABEL values BEFORE we overwrite them, so a
    # coach's correction of an AI tag becomes a recorded (old -> new) signal.
    before_labels: Dict[str, Any] = {}
    after_labels: Dict[str, Any] = {}
    for f, v in changes.items():
        if f in CORRECTABLE_LABEL_FIELDS:
            before_labels[f] = getattr(event, f, None)
            after_labels[f] = v
    if new_extra:
        old_extra = event.extra_data or {}
        for k, v in new_extra.items():
            if k in EXTRA_DATA_LABEL_FIELDS:
                before_labels[k] = old_extra.get(k)
                after_labels[k] = v

    for k, v in changes.items():
        setattr(event, k, v)
    if new_extra is not None:
        from sqlalchemy.orm.attributes import flag_modified
        event.extra_data = {**(event.extra_data or {}), **new_extra}
        flag_modified(event, "extra_data")
    await db.commit()
    await db.refresh(event)

    # Record the correction after the edit is durable. Best-effort — a learning-loop
    # failure must never break the coach's edit, so it's fully guarded.
    label_changes = learning_loop.diff_label_changes(before_labels, after_labels)
    if label_changes:
        try:
            sport = (await db.execute(select(Game.sport).where(Game.id == event.game_id))).scalar_one_or_none()
            manual = (await db.execute(
                select(Organization.learning_loop_manual).where(Organization.id == user.organization_id)
            )).scalar_one_or_none()
            if sport:
                await learning_loop.record_corrections(
                    db, organization_id=user.organization_id, user_id=user.id,
                    event=event, sport=sport, changes=label_changes, manual_mode=bool(manual),
                )
        except Exception:
            pass  # never fail the edit on loop bookkeeping

    return _event_out(event)

@router.delete("/{event_id}")
async def delete_event(event_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Event).where(Event.id == event_id, Event.organization_id == user.organization_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()
    return {"ok": True}
