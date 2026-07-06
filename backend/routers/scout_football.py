"""
Football opponent scouting — manual play-by-play entry, Hudl-style CSV import,
analyze, and the parallel structured retrieval view.

Mirrors the basketball scout router: all input methods land in the shared `events`
table (direct columns + extra_data JSONB), the same substrate film auto-detection
uses, so ONE tendency engine and ONE report pipeline serve every input. No
dedicated per-category tables.

Module-1 intake metadata is stashed on a single `scout_meta` event (side='meta')
so the validation gates can read analyst/reviewer, games scouted, and injury flags
without a new table. The tendency engine ignores non-play events.

Endpoints (prefix /scout/football):
    POST /session              create a football scouting session + intake brief
    POST /plays                rapid play-by-play manual entry -> play_log events
    POST /csv                  import a Hudl-style play log (column-mapped)
    POST /analyze              queue the coordinator scouting report (spec route)
    GET  /{session_id}/analysis  offense/defense/ST + gates + game plan, self-describing
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
from backend.services.tendency_engine import run_tendency_engine

router = APIRouter(prefix="/scout/football", tags=["scout-football"])

# side values the tendency engine splits on. An opponent scout logs the OPPONENT:
# their offense (side=offense), their defense (side=defense), their ST (special_teams).
VALID_SIDES = {"offense", "defense", "special_teams"}


async def _load_session(db: AsyncSession, session_id: str, org_id) -> Game:
    result = await db.execute(
        select(Game).where(Game.id == session_id, Game.organization_id == org_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Football scouting session not found")
    if game.sport != "football":
        raise HTTPException(status_code=422, detail="Session is not a football scouting session")
    return game


# ── session intake (Module 1) ────────────────────────────────────────────────
class SessionCreate(BaseModel):
    opponent: str
    team_name: Optional[str] = None
    game_date: Optional[str] = None
    season: Optional[str] = None
    week: Optional[int] = None
    site: Optional[str] = None                    # home|away|neutral
    team_id: Optional[str] = None
    title: Optional[str] = None

    # Module 1 intelligence brief (all optional — the gates read what is present).
    analyst: Optional[str] = None
    reviewer: Optional[str] = None                # required for Gate 2 (dual review)
    status: Optional[str] = "draft"              # draft|reviewed|final
    games_scouted: Optional[int] = None
    head_coach: Optional[str] = None
    offensive_coordinator: Optional[str] = None
    defensive_coordinator: Optional[str] = None
    weak_schedule: Optional[bool] = None          # strength-of-schedule confidence flag
    weather_note: Optional[str] = None            # wind 15+ mph suppresses deep ball
    injury_flags: Optional[List[str]] = None
    games_with_missing_starter: Optional[List[Any]] = None
    qb_profile: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


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
        title=body.title or f"Football Scouting: {body.opponent}",
        sport="football",
        opponent=body.opponent,
        game_date=gd,
        status="manual",
        is_trial_game=getattr(org, "is_trial", False),
    )
    db.add(game)
    await db.flush()

    # Stash the Module-1 intake on a single meta event (no new table). The engine
    # ignores it (side='meta' is not offense/defense/special_teams); the gates read it.
    meta_event = Event(
        organization_id=org.id,
        game_id=game.id,
        event_type="scout_meta",
        side="meta",
        extra_data={
            "opponent": body.opponent,
            "team_name": body.team_name,
            "season": body.season,
            "week": body.week,
            "site": body.site,
            "analyst_id": body.analyst,
            "analyst": body.analyst,
            "reviewer_id": body.reviewer,
            "reviewer": body.reviewer,
            "status": body.status or "draft",
            "games_scouted": body.games_scouted,
            "head_coach": body.head_coach,
            "offensive_coordinator": body.offensive_coordinator,
            "defensive_coordinator": body.defensive_coordinator,
            "weak_schedule": body.weak_schedule,
            "weather_note": body.weather_note,
            "injury_flags": body.injury_flags or [],
            "games_with_missing_starter": body.games_with_missing_starter or [],
            "qb_profile": body.qb_profile or {},
            "notes": body.notes,
        },
    )
    db.add(meta_event)
    await db.commit()
    await db.refresh(game)

    warnings = []
    if body.games_scouted is not None and body.games_scouted < 3:
        warnings.append("Fewer than 3 games scouted; data confidence is reduced (Gate 1).")
    if not body.reviewer:
        warnings.append("No second-analyst reviewer assigned; report cannot be marked FINAL (Gate 2).")

    return {"session_id": str(game.id), "opponent": game.opponent, "sport": "football",
            "warnings": warnings}


# ── rapid play-by-play entry (Module 2) ──────────────────────────────────────
class PlayEntry(BaseModel):
    # Which side of the ball this play is (opponent offense/defense/ST).
    side: str = "offense"
    game_number: Optional[int] = None
    play_number: Optional[int] = None
    quarter: Optional[int] = None

    # Situational context (direct Event columns).
    down: Optional[int] = None
    distance: Optional[int] = None
    field_position: Optional[str] = None          # e.g. "OWN 35" / "OPP 12"
    hash_position: Optional[str] = None            # left|middle|right
    formation: Optional[str] = None
    personnel: Optional[str] = None                # 11, 12, 21, ...
    play_type: Optional[str] = None
    motion: Optional[bool] = False
    result: Optional[str] = None
    yards_gained: Optional[int] = None
    time_seconds: Optional[float] = None

    # Defensive columns (side == defense).
    defensive_front: Optional[str] = None
    coverage: Optional[str] = None
    blitz: Optional[str] = None

    # Deep-extraction fields (live in extra_data until post-beta column migration).
    run_direction: Optional[str] = None
    run_gap: Optional[str] = None
    run_concept: Optional[str] = None
    pass_concept: Optional[str] = None
    pass_depth: Optional[str] = None
    target_area: Optional[str] = None
    motion_type: Optional[str] = None
    tempo: Optional[str] = None
    score_situation: Optional[str] = None
    coverage_shell: Optional[str] = None
    safety_rotation: Optional[str] = None
    corner_technique: Optional[str] = None
    linebacker_alignment: Optional[str] = None
    pressure_gap: Optional[str] = None
    pressure_type: Optional[str] = None
    is_play_action: Optional[bool] = None
    key_pre_snap_tell: Optional[str] = None

    # Special teams (side == special_teams).
    st_unit: Optional[str] = None                  # Punt|Kickoff|Field Goal|PAT|Punt Return|...
    kick_result: Optional[str] = None
    kick_direction: Optional[str] = None
    fg_distance_yds: Optional[int] = None
    return_scheme: Optional[str] = None
    st_fake: Optional[bool] = None

    primary_player_jersey: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None

    class Config:
        extra = "allow"                            # tolerate extra tags without breaking


_EXTRA_KEYS = (
    "run_direction", "run_gap", "run_concept", "pass_concept", "pass_depth",
    "target_area", "motion_type", "tempo", "score_situation", "coverage_shell",
    "safety_rotation", "corner_technique", "linebacker_alignment", "pressure_gap",
    "pressure_type", "is_play_action", "key_pre_snap_tell", "st_unit", "kick_result",
    "kick_direction", "fg_distance_yds", "return_scheme", "st_fake",
    "primary_player_jersey", "confidence",
)


def _play_to_event(org_id, game_id, p: PlayEntry) -> Event:
    side = p.side if p.side in VALID_SIDES else "offense"
    extra: Dict[str, Any] = {"game_number": p.game_number, "quarter": p.quarter,
                             "play_number": p.play_number, "notes": p.notes}
    for k in _EXTRA_KEYS:
        v = getattr(p, k, None)
        if v is not None:
            extra[k] = v
    return Event(
        organization_id=org_id,
        game_id=game_id,
        event_type="play",
        side=side,
        down=p.down,
        distance=p.distance,
        field_position=p.field_position,
        hash_position=p.hash_position,
        formation=p.formation,
        personnel=p.personnel,
        play_type=p.play_type,
        motion=bool(p.motion),
        result=p.result,
        yards_gained=p.yards_gained,
        time_seconds=p.time_seconds,
        defensive_front=p.defensive_front,
        coverage=p.coverage,
        blitz=p.blitz,
        extra_data={k: v for k, v in extra.items() if v is not None},
    )


class PlaysEntry(BaseModel):
    session_id: str
    plays: List[PlayEntry] = []
    replace: bool = False                          # wipe prior PLAY events first (keeps meta)


@router.post("/plays")
async def enter_plays(
    body: PlaysEntry,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, body.session_id, user.organization_id)

    if body.replace:
        existing = await db.execute(
            select(Event).where(Event.game_id == game.id, Event.event_type == "play")
        )
        for e in existing.scalars().all():
            await db.delete(e)

    objs = [_play_to_event(user.organization_id, game.id, p) for p in body.plays]
    db.add_all(objs)
    await db.commit()

    by_side = {}
    for p in body.plays:
        s = p.side if p.side in VALID_SIDES else "offense"
        by_side[s] = by_side.get(s, 0) + 1
    return {"session_id": str(game.id), "plays_written": len(objs), "by_side": by_side}


# ── Hudl-style CSV play-log import (Module 2) ────────────────────────────────
# Canonical field -> header aliases (case/space/underscore-insensitive).
CSV_FIELD_ALIASES: Dict[str, List[str]] = {
    "odk": ["odk", "od", "phase", "unit"],
    "play_number": ["playnumber", "playno", "play", "no", "num", "#"],
    "down": ["down", "dn", "dwn"],
    "distance": ["distance", "dist", "togo", "dst"],
    "field_position": ["yardline", "yardln", "yrdln", "spot", "los", "fieldposition", "ballon"],
    "hash_position": ["hash", "hashmark"],
    "formation": ["formation", "form", "offform", "offensiveformation"],
    "personnel": ["personnel", "pers", "offpersonnel"],
    "play_type": ["playtype", "type", "playcall", "offplay", "play"],
    "result": ["result", "playresult", "outcome"],
    "yards_gained": ["yardsgained", "yards", "gain", "yds", "gn", "gnls"],
    "defensive_front": ["deffront", "front", "defensivefront"],
    "coverage": ["coverage", "cov", "defcoverage"],
    "blitz": ["blitz", "pressure", "stunt"],
    "quarter": ["quarter", "qtr", "q", "period"],
    "game_number": ["gamenumber", "game", "gameno", "gm"],
    "run_concept": ["runconcept", "runscheme"],
    "pass_concept": ["passconcept", "concept", "route"],
    "motion": ["motion", "mot"],
}


def _norm(h: str) -> str:
    return "".join(ch for ch in (h or "").lower() if ch.isalnum())


def _build_colmap(headers: List[str], override: Optional[Dict[str, str]]) -> Dict[str, str]:
    norm_to_actual = {_norm(h): h for h in headers}
    resolved: Dict[str, str] = {}
    for field, aliases in CSV_FIELD_ALIASES.items():
        if _norm(field) in norm_to_actual:
            resolved[field] = norm_to_actual[_norm(field)]
            continue
        for alias in aliases:
            if _norm(alias) in norm_to_actual:
                resolved[field] = norm_to_actual[_norm(alias)]
                break
    if override:
        for field, header in override.items():
            if header in headers:
                resolved[field] = header
    return resolved


def _odk_to_side(raw: str) -> str:
    """Hudl ODK column: O=offense, D=defense, K=kicking(special teams)."""
    v = (raw or "").strip().lower()
    if v.startswith("d"):
        return "defense"
    if v.startswith("k") or v.startswith("s"):
        return "special_teams"
    return "offense"


class CsvImport(BaseModel):
    session_id: str
    csv_text: str
    column_map: Optional[Dict[str, str]] = None
    default_side: str = "offense"                  # used when no ODK column present
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

    colmap = _build_colmap(list(reader.fieldnames), body.column_map)

    if body.replace:
        existing = await db.execute(
            select(Event).where(Event.game_id == game.id, Event.event_type == "play")
        )
        for e in existing.scalars().all():
            await db.delete(e)

    def cell(row, field):
        header = colmap.get(field)
        return (row.get(header) or "").strip() if header else ""

    def as_int(v):
        if not v:
            return None
        try:
            return int(float(v))
        except ValueError:
            return None

    objs: List[Event] = []
    skipped = 0
    for row in reader:
        # A row needs at least SOME situational or play data to be worth logging.
        odk = cell(row, "odk")
        side = _odk_to_side(odk) if odk else (
            body.default_side if body.default_side in VALID_SIDES else "offense")

        play = PlayEntry(
            side=side,
            game_number=as_int(cell(row, "game_number")),
            play_number=as_int(cell(row, "play_number")),
            quarter=as_int(cell(row, "quarter")),
            down=as_int(cell(row, "down")),
            distance=as_int(cell(row, "distance")),
            field_position=cell(row, "field_position") or None,
            hash_position=cell(row, "hash_position") or None,
            formation=cell(row, "formation") or None,
            personnel=cell(row, "personnel") or None,
            play_type=cell(row, "play_type") or None,
            result=cell(row, "result") or None,
            yards_gained=as_int(cell(row, "yards_gained")),
            defensive_front=cell(row, "defensive_front") or None,
            coverage=cell(row, "coverage") or None,
            blitz=cell(row, "blitz") or None,
            run_concept=cell(row, "run_concept") or None,
            pass_concept=cell(row, "pass_concept") or None,
            motion=(cell(row, "motion").lower() in ("y", "yes", "true", "1")) if cell(row, "motion") else False,
        )
        # Skip fully empty rows.
        if not any([play.down, play.play_type, play.formation, play.result,
                    play.yards_gained is not None]):
            skipped += 1
            continue
        objs.append(_play_to_event(user.organization_id, game.id, play))

    db.add_all(objs)
    await db.commit()
    return {"session_id": str(game.id), "plays_imported": len(objs),
            "rows_skipped": skipped, "columns_matched": colmap}


# ── analyze — the spec route /api/scout/football/analyze ─────────────────────
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

    ev = await db.execute(
        select(Event).where(Event.game_id == game.id, Event.event_type == "play")
    )
    n_plays = len(ev.scalars().all())
    if n_plays == 0:
        raise HTTPException(
            status_code=422,
            detail="No plays logged for this session yet. Add plays via /scout/football/plays or /scout/football/csv first.",
        )

    report = TendencyReport(
        organization_id=org.id,
        team_id=game.team_id,
        game_ids=[str(game.id)],
        sport="football",
        report_type="opponent",
        title=body.title or f"Football Scouting Report: {game.opponent or 'Opponent'}",
        is_trial=getattr(org, "is_trial", False),
        watermarked=getattr(org, "is_trial", False),
    )
    db.add(report)
    await db.flush()
    job = Job(organization_id=org.id, job_type="report", payload={"report_id": str(report.id)})
    db.add(job)
    await db.commit()

    # UATP: identity disclosure + action logging (the football scouting agent starts).
    await log_agent_action(
        action="queue_football_scouting_report",
        game_id=str(game.id),
        organization_id=str(org.id),
        job_id=str(job.id),
        phase="scout",
        reason=f"Football coordinator scouting report queued from {n_plays} logged plays.",
        level="info",
        detail={"report_id": str(report.id), "plays": n_plays, "opponent": game.opponent},
    )
    return {"report_id": str(report.id), "session_id": str(game.id),
            "status": "queued", "plays": n_plays,
            "preliminary": n_plays < 60}


# ── parallel structured retrieval — offense / defense / ST + gates + plan ─────
@router.get("/{session_id}/analysis")
async def football_analysis(
    session_id: str,
    block: Optional[str] = None,   # optional: offense|defense|special_teams|gates|game_plan
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the football scouting analysis as discrete, self-describing blocks
    computed fresh from this session's plays. This is the PARALLEL view: each block
    (offense, defense, special_teams, validation gates, game_plan) is retrievable on
    its own (pass ?block=game_plan), fully self-describing (sport + opponent), so
    there is no chance of confusing one sport's data with another's.

    Distinct from /analyze, which queues the combined coach-facing prose report.
    """
    game = await _load_session(db, session_id, user.organization_id)

    ev = await db.execute(select(Event).where(Event.game_id == game.id))
    events = ev.scalars().all()

    summary = await run_tendency_engine("football", events)
    scouting = summary.get("scouting", {}) or {}

    blocks = {
        "offense": summary.get("offense", {}),
        "defense": summary.get("defense", {}),
        "special_teams": summary.get("special_teams", {}),
        "gates": {
            "report_status": scouting.get("report_status"),
            "validation_gates": scouting.get("validation_gates", []),
        },
        "game_plan": {
            "game_plan": scouting.get("game_plan", {}),
            "situational_tendencies": scouting.get("situational_tendencies", []),
            "head_coach_priorities": scouting.get("head_coach_priorities", []),
        },
    }

    if block:
        if block not in blocks:
            raise HTTPException(status_code=404,
                                detail=f"Unknown block '{block}'. Valid: {', '.join(blocks)}")
        selected = {block: blocks[block]}
    else:
        selected = blocks

    return {
        "session_id": str(game.id),
        "sport": "football",                       # always the discriminator, echoed back
        "opponent": game.opponent,
        "report_status": scouting.get("report_status", "PRELIMINARY"),
        "total_plays": scouting.get("total_plays", summary.get("total_plays", 0)),
        "games_scouted": scouting.get("games_scouted", 1),
        "personnel_flagged": scouting.get("personnel_flagged", False),
        "blocks": selected,
    }
