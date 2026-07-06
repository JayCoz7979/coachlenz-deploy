"""
Opponent scouting ingestion (basketball) — manual entry, CSV import, and analyze.

All three input methods land in the shared `events` table (extra_data JSONB), the
same substrate film auto-detection uses, so one tendency engine and one report
pipeline serve every input. No dedicated per-category tables.

Endpoints:
    POST /scout/session   create a scouting session (a basketball game shell)
    POST /scout/manual    write per-player aggregates + optional granular events
    POST /scout/csv       import a standard box score (column-mapped) -> player_stat rows
    POST /scout/analyze   queue the six-category scouting report for a session
"""
import csv
import io
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.models.event import Event
from backend.models.job import Job
from backend.models.report import TendencyReport
from backend.services.auth import get_current_user, get_current_org
from backend.services.agent_log import log_agent_action

router = APIRouter(prefix="/scout", tags=["scout"])

# The ten court zones, mirrored from the engine so the API can validate/derive.
THREE_ZONES = {
    "Left Corner 3", "Right Corner 3",
    "Above-the-Break 3 Left", "Above-the-Break 3 Right", "Above-the-Break 3 Center",
}


def _shot_type_for_zone(zone: Optional[str], explicit: Optional[str]) -> str:
    if explicit in ("2pt", "3pt"):
        return explicit
    return "3pt" if (zone or "") in THREE_ZONES else "2pt"


async def _load_session(db: AsyncSession, session_id: str, org_id) -> Game:
    result = await db.execute(
        select(Game).where(Game.id == session_id, Game.organization_id == org_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Scouting session not found")
    return game


# ── session ─────────────────────────────────────────────────────────────────
class SessionCreate(BaseModel):
    opponent: str
    team_name: Optional[str] = None          # our team preparing the scout
    game_date: Optional[str] = None          # ISO date string
    season: Optional[str] = None
    team_id: Optional[str] = None
    title: Optional[str] = None


@router.post("/session")
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    gd = None
    if body.game_date:
        try:
            gd = date.fromisoformat(body.game_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="game_date must be ISO format YYYY-MM-DD")

    game = Game(
        organization_id=org.id,
        team_id=body.team_id,
        title=body.title or f"Scouting: {body.opponent}",
        sport="basketball",
        opponent=body.opponent,
        game_date=gd,
        status="manual",
        is_trial_game=getattr(org, "is_trial", False),
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return {"session_id": str(game.id), "opponent": game.opponent, "sport": "basketball"}


# ── manual entry ─────────────────────────────────────────────────────────────
class PlayerStat(BaseModel):
    jersey_number: str
    player_name: Optional[str] = None
    possession_time_seconds: float = 0
    touches: int = 0
    turnovers: int = 0
    deflections: int = 0
    shot_attempts_2pt: int = 0
    shot_makes_2pt: int = 0
    shot_attempts_3pt: int = 0
    shot_makes_3pt: int = 0


class ShotEntry(BaseModel):
    jersey_number: str
    court_zone: str
    made: bool = False
    shot_type: Optional[str] = None            # derived from zone if omitted
    possession_origin: Optional[str] = None    # half_court|transition|set|broken|pnr
    quarter: Optional[int] = None
    possession_seconds: Optional[float] = None
    score_diff_at_start: Optional[int] = None


class TurnoverEntry(BaseModel):
    jersey_number: str
    turnover_type: str                          # live_ball_steal|bad_pass|charge|travel|shot_clock|out_of_bounds
    game_situation: Optional[str] = None        # half_court|transition|press|late_game
    generated_by_defender: Optional[str] = None
    quarter: Optional[int] = None


class DeflectionEntry(BaseModel):
    jersey_number: str                          # the defender
    deflection_type: str                        # tipped_pass|contested_catch|redirected_dribble
    resulted_in_possession_change: bool = False
    passing_lane: Optional[str] = None
    quarter: Optional[int] = None


class PossessionEntry(BaseModel):
    possession_seconds: float
    side: str = "offense"                        # offense|defense
    possession_origin: Optional[str] = None
    score_diff_at_start: Optional[int] = None
    quarter: Optional[int] = None
    jersey_number: Optional[str] = None          # initiator


class ManualEntry(BaseModel):
    session_id: str
    players: List[PlayerStat] = []
    shots: List[ShotEntry] = []
    turnovers: List[TurnoverEntry] = []
    deflections: List[DeflectionEntry] = []
    possessions: List[PossessionEntry] = []
    replace: bool = False                        # wipe prior events for this session first


def _player_stat_event(org_id, game_id, p: PlayerStat) -> Event:
    return Event(
        organization_id=org_id,
        game_id=game_id,
        event_type="player_stat",
        side="offense",
        extra_data={
            "primary_player_jersey": str(p.jersey_number),
            "player_name": p.player_name,
            "possession_time_seconds": p.possession_time_seconds,
            "touches": p.touches,
            "turnovers": p.turnovers,
            "deflections": p.deflections,
            "shot_attempts_2pt": p.shot_attempts_2pt,
            "shot_makes_2pt": p.shot_makes_2pt,
            "shot_attempts_3pt": p.shot_attempts_3pt,
            "shot_makes_3pt": p.shot_makes_3pt,
            "players": [{"jersey": str(p.jersey_number), "team": "offense", "role": "primary"}],
        },
    )


@router.post("/manual")
async def manual_entry(
    body: ManualEntry,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, body.session_id, user.organization_id)

    if body.replace:
        existing = await db.execute(select(Event).where(Event.game_id == game.id))
        for e in existing.scalars().all():
            await db.delete(e)

    objs: List[Event] = []

    for p in body.players:
        objs.append(_player_stat_event(user.organization_id, game.id, p))

    for s in body.shots:
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="shot",
            side="offense",
            result="made" if s.made else "missed",
            time_seconds=None,
            extra_data={
                "primary_player_jersey": str(s.jersey_number),
                "shot_zone": s.court_zone,
                "shot_type": _shot_type_for_zone(s.court_zone, s.shot_type),
                "possession_origin": s.possession_origin,
                "quarter": s.quarter,
                "possession_seconds": s.possession_seconds,
                "score_diff_at_start": s.score_diff_at_start,
                "players": [{"jersey": str(s.jersey_number), "team": "offense", "role": "shooter"}],
            },
        ))

    for t in body.turnovers:
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="turnover",
            side="offense",
            extra_data={
                "primary_player_jersey": str(t.jersey_number),
                "turnover_type": t.turnover_type,
                "game_situation": t.game_situation,
                "generated_by_defender": t.generated_by_defender,
                "quarter": t.quarter,
                "players": [{"jersey": str(t.jersey_number), "team": "offense", "role": "primary"}],
            },
        ))

    for d in body.deflections:
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="deflection",
            side="defense",
            result="possession_change" if d.resulted_in_possession_change else None,
            extra_data={
                "primary_player_jersey": str(d.jersey_number),
                "deflection_type": d.deflection_type,
                "resulted_in_possession_change": d.resulted_in_possession_change,
                "passing_lane": d.passing_lane,
                "quarter": d.quarter,
                "players": [{"jersey": str(d.jersey_number), "team": "defense", "role": "deflector"}],
            },
        ))

    for pos in body.possessions:
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="possession",
            side=pos.side,
            extra_data={
                "primary_player_jersey": str(pos.jersey_number) if pos.jersey_number else None,
                "possession_seconds": pos.possession_seconds,
                "possession_origin": pos.possession_origin,
                "score_diff_at_start": pos.score_diff_at_start,
                "quarter": pos.quarter,
            },
        ))

    db.add_all(objs)
    await db.commit()
    return {
        "session_id": str(game.id),
        "events_written": len(objs),
        "breakdown": {
            "player_stats": len(body.players),
            "shots": len(body.shots),
            "turnovers": len(body.turnovers),
            "deflections": len(body.deflections),
            "possessions": len(body.possessions),
        },
    }


# ── CSV box-score import ─────────────────────────────────────────────────────
# Canonical field -> the header aliases we auto-detect (case/space/underscore-insensitive).
CSV_FIELD_ALIASES: Dict[str, List[str]] = {
    "jersey_number": ["jersey", "number", "no", "num", "#"],
    "player_name": ["player", "name", "playername"],
    "possession_time_seconds": ["possessionseconds", "possessiontime", "posssec", "timeofpossession", "top"],
    "touches": ["touches", "touch"],
    "turnovers": ["turnovers", "to", "tov", "to#"],
    "deflections": ["deflections", "defl", "def"],
    "shot_attempts_2pt": ["fg2a", "2pa", "twopa", "2ptattempts", "2ptatt"],
    "shot_makes_2pt": ["fg2m", "2pm", "twopm", "2ptmade"],
    "shot_attempts_3pt": ["fg3a", "3pa", "threepa", "3ptattempts", "3ptatt"],
    "shot_makes_3pt": ["fg3m", "3pm", "threepm", "3ptmade"],
}
_INT_FIELDS = {
    "touches", "turnovers", "deflections",
    "shot_attempts_2pt", "shot_makes_2pt", "shot_attempts_3pt", "shot_makes_3pt",
}


def _norm_header(h: str) -> str:
    return "".join(ch for ch in (h or "").lower() if ch.isalnum())


def _build_column_map(headers: List[str], override: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Map canonical field -> actual header. `override` (field -> header) wins."""
    norm_to_actual = {_norm_header(h): h for h in headers}
    resolved: Dict[str, str] = {}

    for field, aliases in CSV_FIELD_ALIASES.items():
        # exact field-name match first
        if _norm_header(field) in norm_to_actual:
            resolved[field] = norm_to_actual[_norm_header(field)]
            continue
        for alias in aliases:
            if _norm_header(alias) in norm_to_actual:
                resolved[field] = norm_to_actual[_norm_header(alias)]
                break

    if override:
        for field, header in override.items():
            if header in headers:
                resolved[field] = header
    return resolved


class CsvImport(BaseModel):
    session_id: str
    csv_text: str
    column_map: Optional[Dict[str, str]] = None    # canonical_field -> header override
    replace: bool = False


@router.post("/csv")
async def csv_import(
    body: CsvImport,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, body.session_id, user.organization_id)

    reader = csv.DictReader(io.StringIO(body.csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV has no header row")

    colmap = _build_column_map(list(reader.fieldnames), body.column_map)
    if "jersey_number" not in colmap:
        raise HTTPException(
            status_code=422,
            detail="Could not find a jersey/number column. Pass column_map to map it explicitly.",
        )

    if body.replace:
        existing = await db.execute(select(Event).where(Event.game_id == game.id))
        for e in existing.scalars().all():
            await db.delete(e)

    def cell(row, field):
        header = colmap.get(field)
        if not header:
            return None
        return (row.get(header) or "").strip()

    def as_num(v, integer=False):
        if v in (None, ""):
            return 0 if integer else 0.0
        try:
            return int(float(v)) if integer else float(v)
        except ValueError:
            return 0 if integer else 0.0

    objs: List[Event] = []
    skipped = 0
    for row in reader:
        jersey = cell(row, "jersey_number")
        if not jersey:
            skipped += 1
            continue
        p = PlayerStat(
            jersey_number=str(jersey),
            player_name=cell(row, "player_name") or None,
            possession_time_seconds=as_num(cell(row, "possession_time_seconds")),
            touches=as_num(cell(row, "touches"), integer=True),
            turnovers=as_num(cell(row, "turnovers"), integer=True),
            deflections=as_num(cell(row, "deflections"), integer=True),
            shot_attempts_2pt=as_num(cell(row, "shot_attempts_2pt"), integer=True),
            shot_makes_2pt=as_num(cell(row, "shot_makes_2pt"), integer=True),
            shot_attempts_3pt=as_num(cell(row, "shot_attempts_3pt"), integer=True),
            shot_makes_3pt=as_num(cell(row, "shot_makes_3pt"), integer=True),
        )
        objs.append(_player_stat_event(user.organization_id, game.id, p))

    db.add_all(objs)
    await db.commit()
    return {
        "session_id": str(game.id),
        "players_imported": len(objs),
        "rows_skipped": skipped,
        "columns_matched": colmap,
    }


# ── analyze (spec alias for /api/scout/analyze) ──────────────────────────────
class AnalyzeRequest(BaseModel):
    session_id: str
    title: Optional[str] = None


@router.post("/analyze")
async def analyze(
    body: AnalyzeRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, body.session_id, org.id)

    count = await db.execute(select(Event).where(Event.game_id == game.id))
    n_events = len(count.scalars().all())
    if n_events == 0:
        raise HTTPException(
            status_code=422,
            detail="No scouting data for this session yet. Add stats via /scout/manual or /scout/csv first.",
        )

    report = TendencyReport(
        organization_id=org.id,
        team_id=game.team_id,
        game_ids=[str(game.id)],
        sport="basketball",
        report_type="opponent",
        title=body.title or f"Scouting Report: {game.opponent or 'Opponent'}",
        is_trial=getattr(org, "is_trial", False),
        watermarked=getattr(org, "is_trial", False),
    )
    db.add(report)
    await db.flush()
    job = Job(organization_id=org.id, job_type="report", payload={"report_id": str(report.id)})
    db.add(job)
    await db.commit()

    # UATP: identity disclosure + action logging (the scouting agent is starting).
    await log_agent_action(
        action="queue_scouting_report",
        game_id=str(game.id),
        organization_id=str(org.id),
        job_id=str(job.id),
        phase="scout",
        reason=f"Six-category opponent scouting report queued from {n_events} tagged events.",
        level="info",
        detail={"report_id": str(report.id), "events": n_events, "opponent": game.opponent},
    )

    return {"report_id": str(report.id), "session_id": str(game.id), "status": "queued", "events": n_events}
