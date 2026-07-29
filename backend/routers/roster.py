"""
Team roster management + jersey-to-player resolution (Track 3.3).

Rosters are org-scoped through their team (which carries season + sport). Player
names live here and are never exposed on public share links (see reports share
endpoint, which returns jerseys/tendencies only).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.models.team import Team
from backend.models.game import Game
from backend.models.event import Event
from backend.models.roster import RosterPlayer
from backend.services.auth import get_current_user, require_permission
from backend.services.permissions import CAN_MANAGE_ROSTER
from backend.services.roster import parse_roster_csv, resolve_jersey, normalize_jersey

# Managing the roster (add/edit/remove/upload/clone) requires the can_manage_roster
# capability (head coach, coordinators, owner). Reads stay open to any org member.
_require_manage = Depends(require_permission(CAN_MANAGE_ROSTER))

router = APIRouter(prefix="/rosters", tags=["rosters"])


class PlayerIn(BaseModel):
    jersey_number: str
    first_name: str
    last_name: Optional[str] = None
    position: Optional[str] = None
    grade_year: Optional[str] = None


class PlayerPatch(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    position: Optional[str] = None
    grade_year: Optional[str] = None
    is_active: Optional[bool] = None


class CsvIn(BaseModel):
    csv: str


def _player_out(p: RosterPlayer) -> dict:
    return {"id": str(p.id), "jersey_number": p.jersey_number, "first_name": p.first_name,
            "last_name": p.last_name, "position": p.position, "grade_year": p.grade_year,
            "is_active": p.is_active}


async def _team_or_404(team_id: str, user: User, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(
        Team.id == team_id, Team.organization_id == user.organization_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


async def _roster(team_id: str, org_id, db: AsyncSession):
    res = await db.execute(select(RosterPlayer).where(
        RosterPlayer.team_id == team_id, RosterPlayer.organization_id == org_id
    ).order_by(RosterPlayer.jersey_number))
    return res.scalars().all()


@router.get("/{team_id}")
async def list_roster(team_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team = await _team_or_404(team_id, user, db)
    players = await _roster(team_id, user.organization_id, db)
    return {"team_id": str(team.id), "team": team.name, "season": team.season,
            "sport": team.sport, "players": [_player_out(p) for p in players]}


@router.post("/{team_id}/players")
async def add_player(team_id: str, body: PlayerIn, user: User = _require_manage, db: AsyncSession = Depends(get_db)):
    await _team_or_404(team_id, user, db)
    jersey = normalize_jersey(body.jersey_number)
    if not jersey:
        raise HTTPException(status_code=422, detail="Jersey number is required.")
    existing = await db.execute(select(RosterPlayer).where(
        RosterPlayer.team_id == team_id, RosterPlayer.jersey_number == jersey))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Jersey #{jersey} is already on this roster.")
    p = RosterPlayer(organization_id=user.organization_id, team_id=team_id, jersey_number=jersey,
                     first_name=body.first_name, last_name=body.last_name,
                     position=body.position, grade_year=body.grade_year)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _player_out(p)


@router.post("/{team_id}/upload")
async def upload_roster_csv(team_id: str, body: CsvIn, user: User = _require_manage, db: AsyncSession = Depends(get_db)):
    """Upsert a roster from CSV (columns: jersey_number, first_name, last_name,
    position, grade_year — common header spellings accepted). Existing jerseys are
    updated in place; new ones are inserted."""
    await _team_or_404(team_id, user, db)
    try:
        parsed = parse_roster_csv(body.csv)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    current = {p.jersey_number: p for p in await _roster(team_id, user.organization_id, db)}
    created = updated = 0
    for row in parsed:
        j = row["jersey_number"]
        if j in current:
            p = current[j]
            p.first_name, p.last_name = row["first_name"], row["last_name"]
            p.position, p.grade_year = row["position"], row["grade_year"]
            updated += 1
        else:
            p = RosterPlayer(organization_id=user.organization_id, team_id=team_id, **row)
            db.add(p)
            current[j] = p
            created += 1
    await db.commit()
    return {"ok": True, "created": created, "updated": updated, "total_in_csv": len(parsed)}


@router.patch("/{team_id}/players/{player_id}")
async def edit_player(team_id: str, player_id: str, body: PlayerPatch, user: User = _require_manage, db: AsyncSession = Depends(get_db)):
    await _team_or_404(team_id, user, db)
    res = await db.execute(select(RosterPlayer).where(
        RosterPlayer.id == player_id, RosterPlayer.team_id == team_id,
        RosterPlayer.organization_id == user.organization_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    await db.commit()
    return _player_out(p)


@router.delete("/{team_id}/players/{player_id}")
async def remove_player(team_id: str, player_id: str, user: User = _require_manage, db: AsyncSession = Depends(get_db)):
    await _team_or_404(team_id, user, db)
    res = await db.execute(select(RosterPlayer).where(
        RosterPlayer.id == player_id, RosterPlayer.team_id == team_id,
        RosterPlayer.organization_id == user.organization_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.post("/{team_id}/clone-to/{target_team_id}")
async def clone_roster(team_id: str, target_team_id: str, user: User = _require_manage, db: AsyncSession = Depends(get_db)):
    """Copy this roster to another team (e.g. a new season). Jerseys already present
    on the target are left untouched."""
    await _team_or_404(team_id, user, db)
    await _team_or_404(target_team_id, user, db)
    source = await _roster(team_id, user.organization_id, db)
    existing = {p.jersey_number for p in await _roster(target_team_id, user.organization_id, db)}
    cloned = 0
    for p in source:
        if p.jersey_number in existing:
            continue
        db.add(RosterPlayer(organization_id=user.organization_id, team_id=target_team_id,
                            jersey_number=p.jersey_number, first_name=p.first_name,
                            last_name=p.last_name, position=p.position, grade_year=p.grade_year))
        cloned += 1
    await db.commit()
    return {"ok": True, "cloned": cloned, "skipped_existing": len(source) - cloned}


@router.get("/resolve/game/{game_id}")
async def resolve_game_jerseys(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Map the jersey numbers detected in a game's plays to named roster players
    (jersey-to-player auto-assign). Returns each distinct jersey with its player, or
    null when the jersey isn't on the roster."""
    gres = await db.execute(select(Game).where(
        Game.id == game_id, Game.organization_id == user.organization_id))
    game = gres.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not game.team_id:
        return {"game_id": game_id, "team_id": None, "links": [],
                "message": "Assign this game to a team to auto-link jerseys to your roster."}

    roster = await _roster(str(game.team_id), user.organization_id, db)

    eres = await db.execute(select(Event).where(
        Event.game_id == game_id, Event.organization_id == user.organization_id,
        Event.event_type != "scout_meta"))
    events = eres.scalars().all()

    jerseys = set()
    for e in events:
        if e.player:
            jerseys.add(normalize_jersey(e.player))
        for p in ((e.extra_data or {}).get("players") or []):
            if isinstance(p, dict) and p.get("jersey"):
                jerseys.add(normalize_jersey(p["jersey"]))

    links = []
    for j in sorted(x for x in jerseys if x):
        match = resolve_jersey(roster, j)
        links.append({
            "jersey_number": j,
            "player": (_player_out(match) if match else None),
        })
    return {"game_id": game_id, "team_id": str(game.team_id), "links": links}
