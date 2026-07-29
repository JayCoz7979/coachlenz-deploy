"""
Player Grades Board (Track 5.3). Aggregates the technique-grade pass output (stored
per play in Event.extra_data.player_grades) into a board by player / position group /
play type, a printable weekly grade sheet, a CSV export, and per-grade coach notes.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.models.game import Game
from backend.models.event import Event
from backend.models.roster import RosterPlayer
from backend.models.grade_annotation import GradeAnnotation
from backend.services.auth import get_current_user, require_permission
from backend.services.permissions import CAN_MANAGE_ROSTER
from backend.services.roster import normalize_jersey
from backend.services.grades import (
    extract_player_grades, aggregate_grades, build_grade_sheet, grade_sheet_to_csv,
)

router = APIRouter(prefix="/grades", tags=["grades"])

_require_manage = Depends(require_permission(CAN_MANAGE_ROSTER))


async def _game_or_404(game_id: str, user: User, db: AsyncSession) -> Game:
    res = await db.execute(select(Game).where(
        Game.id == game_id, Game.organization_id == user.organization_id))
    game = res.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


async def _events(game_id: str, org_id, db: AsyncSession):
    res = await db.execute(select(Event).where(
        Event.game_id == game_id, Event.organization_id == org_id,
        Event.event_type != "scout_meta"))
    return res.scalars().all()


async def _roster_names(team_id, org_id, db: AsyncSession) -> dict:
    if not team_id:
        return {}
    res = await db.execute(select(RosterPlayer).where(
        RosterPlayer.team_id == team_id, RosterPlayer.organization_id == org_id))
    names = {}
    for p in res.scalars().all():
        names[normalize_jersey(p.jersey_number)] = f"{p.first_name} {p.last_name or ''}".strip()
    return names


@router.get("/game/{game_id}")
async def grades_board(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    game = await _game_or_404(game_id, user, db)
    rows = extract_player_grades(await _events(game_id, user.organization_id, db))
    names = await _roster_names(game.team_id, user.organization_id, db)
    return {"game_id": game_id, "graded_plays": len(rows), **aggregate_grades(rows, names)}


@router.get("/game/{game_id}/sheet")
async def grade_sheet(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    game = await _game_or_404(game_id, user, db)
    rows = extract_player_grades(await _events(game_id, user.organization_id, db))
    names = await _roster_names(game.team_id, user.organization_id, db)
    return build_grade_sheet(rows, names)


@router.get("/game/{game_id}/export")
async def grade_sheet_export(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    game = await _game_or_404(game_id, user, db)
    rows = extract_player_grades(await _events(game_id, user.organization_id, db))
    names = await _roster_names(game.team_id, user.organization_id, db)
    csv_text = grade_sheet_to_csv(build_grade_sheet(rows, names))
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="grade-sheet-{game_id}.csv"'})


class AnnotationIn(BaseModel):
    game_id: str
    event_id: str
    jersey: Optional[str] = None
    note: str


@router.post("/annotations")
async def add_annotation(body: AnnotationIn, coach: User = _require_manage, db: AsyncSession = Depends(get_db)):
    """Attach a coach's note to a player's grade on a specific play (event)."""
    game = await _game_or_404(body.game_id, coach, db)
    eres = await db.execute(select(Event).where(
        Event.id == body.event_id, Event.game_id == game.id,
        Event.organization_id == coach.organization_id))
    if not eres.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Play not found in this game.")
    if not (body.note or "").strip():
        raise HTTPException(status_code=422, detail="Note cannot be empty.")
    ann = GradeAnnotation(
        organization_id=coach.organization_id, game_id=game.id, event_id=body.event_id,
        jersey=(normalize_jersey(body.jersey) if body.jersey else None),
        note=body.note.strip(), created_by=coach.id)
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return {"id": str(ann.id), "event_id": body.event_id, "jersey": ann.jersey, "note": ann.note}


@router.get("/game/{game_id}/annotations")
async def list_annotations(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _game_or_404(game_id, user, db)
    res = await db.execute(select(GradeAnnotation).where(
        GradeAnnotation.game_id == game_id,
        GradeAnnotation.organization_id == user.organization_id
    ).order_by(GradeAnnotation.created_at))
    return [{"id": str(a.id), "event_id": str(a.event_id), "jersey": a.jersey,
             "note": a.note, "created_by": str(a.created_by) if a.created_by else None,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in res.scalars().all()]
