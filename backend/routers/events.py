from fastapi import APIRouter, Depends, HTTPException, Response
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
from backend.services import play_enrich
from backend.services.agent_log import log_agent_action

router = APIRouter(prefix="/events", tags=["events"])


async def _load_game_plays(db: AsyncSession, game_id: str, org_id):
    """Load a game (org-scoped) and its PLAY events in a stable order. The order
    (time, then id) is the SAME for the template export and the play_index matcher,
    so a row's play_index always points at the same play on both ends."""
    g = await db.execute(select(Game).where(Game.id == game_id, Game.organization_id == org_id))
    game = g.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    res = await db.execute(
        select(Event)
        .where(Event.game_id == game_id, Event.organization_id == org_id, Event.event_type == "play")
        .order_by(Event.time_seconds.asc().nullslast(), Event.id)
    )
    return game, res.scalars().all()


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

# ── Situational CSV enrichment ───────────────────────────────────────────────
# Add down/distance/spot to AI-detected plays that came off scoreboard-less film,
# WITHOUT creating or deleting plays. Two steps: download a template of the game's
# plays, fill the situational columns from film, upload it back.

@router.get("/enrich-template")
async def enrich_template(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Download a CSV of this game's detected plays: event_id + play context +
    blank (or current) situational columns for the coach to fill from film."""
    game, plays = await _load_game_plays(db, game_id, user.organization_id)
    rows = [{
        "event_id": e.id, "time_seconds": e.time_seconds, "side": e.side,
        "formation": e.formation, "personnel": e.personnel, "play_type": e.play_type,
        "yards_gained": e.yards_gained, "down": e.down, "distance": e.distance,
        "field_position": e.field_position, "hash_position": e.hash_position,
    } for e in plays]
    csv_text = play_enrich.build_template_csv(rows)
    fname = f"plays-enrich-{str(game.id)[:8]}.csv"
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class EnrichCSV(BaseModel):
    game_id: str
    csv_text: str


@router.post("/enrich-csv")
async def enrich_csv(body: EnrichCSV, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Apply a filled template: set ONLY situational columns (down/distance/spot/hash)
    on the matched existing plays. Never creates or deletes a play, so the AI's
    formation/personnel/concept/jersey reads are preserved. Rows match by event_id
    (preferred) or play_index; a row with any bad cell is skipped whole (no partial
    apply) and reported back so the coach can fix and re-upload."""
    game, plays = await _load_game_plays(db, body.game_id, user.organization_id)
    parsed = play_enrich.parse_enrichment_csv(body.csv_text)
    if parsed["header_error"]:
        raise HTTPException(status_code=422, detail=parsed["header_error"])

    by_id = {str(e.id): e for e in plays}
    by_idx = {i: e for i, e in enumerate(plays, 1)}

    updated = 0
    fields_set: Dict[str, int] = {}
    row_errors = []
    unmatched = 0
    for r in parsed["rows"]:
        if r["errors"]:
            row_errors.append({"line": r["line"], "errors": r["errors"]})
            continue
        ev = by_id.get(str(r["key"])) if r["key_type"] == "event_id" else by_idx.get(r["key"])
        if ev is None:
            unmatched += 1
            row_errors.append({"line": r["line"], "errors": [f"no matching play for {r['key_type']}={r['key']}"]})
            continue
        changed = False
        for f, v in r["fields"].items():
            if getattr(ev, f) != v:
                setattr(ev, f, v)
                fields_set[f] = fields_set.get(f, 0) + 1
                changed = True
        if changed:
            updated += 1

    await db.commit()

    with_down = sum(1 for e in plays if e.down is not None)
    # UATP: identity disclosure + action logging (best-effort, never raises).
    await log_agent_action(
        action="enrich_plays_csv",
        game_id=str(game.id),
        organization_id=str(user.organization_id),
        phase="scout",
        reason=f"Coach added situational data to {updated} detected plays via CSV "
               f"({with_down}/{len(plays)} now have down/distance).",
        level="info",
        detail={"updated": updated, "fields_set": fields_set,
                "unmatched": unmatched, "row_errors": len(row_errors)},
    )

    return {
        "game_id": str(game.id),
        "plays_total": len(plays),
        "plays_updated": updated,
        "fields_set": fields_set,
        "unmatched_rows": unmatched,
        "row_errors": row_errors[:50],
        "plays_with_down": with_down,
        "columns_matched": [k for k in parsed["colmap"].keys() if k in play_enrich.ENRICHABLE_FIELDS],
        "hint": "Regenerate the report to pick up the new down/distance tendencies "
                "(the carry-forward inference fills gaps within each drive).",
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
