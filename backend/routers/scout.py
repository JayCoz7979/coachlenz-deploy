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
from backend.services.auth import (
    get_current_user, get_current_org, can_review_scout, require_scout_reviewer,
)
from backend.services.agent_log import log_agent_action
from backend.services.sports import assert_sport_allowed
from backend.services.tendency_engine import run_tendency_engine
from backend.services.tendency_engine.basketball_scout import build_scouting_report

# The six scouting categories in strict priority order (Category 1 heaviest).
# Maps the engine's internal keys to a clean, self-describing label so each
# category can be consumed on its own, in parallel, with no risk of confusion.
SCOUT_CATEGORIES = [
    (1, "time_of_possession", "Time of Possession (Player)", "category_1_time_of_possession"),
    (2, "turnovers", "Turnovers", "category_2_turnovers"),
    (3, "deflections", "Deflections", "category_3_deflections"),
    (4, "shot_ratio", "2PT vs 3PT Shot Ratio", "category_4_shot_ratio"),
    (5, "pace", "Pace of Play", "category_5_pace"),
    (6, "scoring_areas", "Scoring Areas (eFG% by Zone)", "category_6_scoring_areas"),
]

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


async def _load_meta_event(db: AsyncSession, game_id) -> Optional[Event]:
    """The single side='meta' event that holds the Module-1 intake + review state."""
    result = await db.execute(
        select(Event).where(Event.game_id == game_id, Event.event_type == "scout_meta")
    )
    return result.scalar_one_or_none()


async def _authorized_session(db: AsyncSession, session_id: str, user: User,
                              write: bool = False) -> Game:
    """Load a session and enforce scouting RLS (mirrors the football scout):

    • The primary analyst (session creator) may read AND write their own session.
    • Any reviewer-authorized user (head coach / coordinator / reviewer / owner)
      may read every session in the org, and may write.
    • A different plain analyst/member may NOT touch someone else's session.

    This is what gives Gate 2 teeth: identity is the token, not a form field.
    Legacy/film-only sessions with no recorded analyst fall back to org-scope.
    """
    game = await _load_session(db, session_id, user.organization_id)
    meta = await _load_meta_event(db, game.id)
    analyst_id = (meta.extra_data or {}).get("analyst_id") if meta else None

    is_analyst = analyst_id is not None and str(analyst_id) == str(user.id)
    if is_analyst or can_review_scout(user) or analyst_id is None:
        return game
    raise HTTPException(
        status_code=403,
        detail="This scouting session belongs to another analyst. Ask a reviewer or the session owner.",
    )


# ── session intake (Module 1 + single-camera calibration) ────────────────────
class SessionCreate(BaseModel):
    opponent: str
    team_name: Optional[str] = None          # our team preparing the scout
    game_date: Optional[str] = None          # ISO date string
    season: Optional[str] = None
    team_id: Optional[str] = None
    title: Optional[str] = None

    # Module 1 intelligence brief (all optional — the gates read what is present).
    # NOTE: analyst identity is NOT taken from the client — it is set server-side
    # from the authenticated user so Gate 2 (dual review) cannot be spoofed.
    games_scouted: Optional[int] = None
    head_coach: Optional[str] = None
    offensive_system: Optional[str] = None
    defensive_system: Optional[str] = None
    weak_schedule: Optional[bool] = None          # strength-of-schedule confidence flag
    injury_flags: Optional[List[str]] = None
    games_with_missing_starter: Optional[List[Any]] = None
    notes: Optional[str] = None

    # Single-camera calibration note (required per the charter for every game;
    # optional at the API boundary so a film-only session still works).
    camera_angle: Optional[str] = None            # high-wide | sideline | end-zone
    camera_quality: Optional[str] = None          # clear | standard | poor
    visibility_rating: Optional[str] = None       # FULL | PARTIAL | LIMITED
    off_ball_visibility_pct: Optional[float] = None  # % of possessions all 5 visible


@router.post("/session")
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    assert_sport_allowed(org, "basketball")
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
    await db.flush()

    # Stash the Module-1 intake + camera calibration on a single meta event (no new
    # table). The six-category engine ignores side='meta'; the validation gates and
    # the camera-confidence summary read it.
    meta_event = Event(
        organization_id=org.id,
        game_id=game.id,
        event_type="scout_meta",
        side="meta",
        extra_data={
            "opponent": body.opponent,
            "team_name": body.team_name,
            "season": body.season,
            # Identity is server-set from the authenticated user (anti-spoof).
            "analyst_id": str(user.id),
            "analyst": user.name,
            "reviewer_id": None,          # set only by a real /review sign-off
            "reviewer": None,
            "status": "draft",            # only /review can advance this
            "games_scouted": body.games_scouted,
            "head_coach": body.head_coach,
            "offensive_system": body.offensive_system,
            "defensive_system": body.defensive_system,
            "weak_schedule": body.weak_schedule,
            "injury_flags": body.injury_flags or [],
            "games_with_missing_starter": body.games_with_missing_starter or [],
            "notes": body.notes,
            "camera_angle": body.camera_angle,
            "camera_quality": body.camera_quality,
            "visibility_rating": body.visibility_rating,
            "off_ball_visibility_pct": body.off_ball_visibility_pct,
        },
    )
    db.add(meta_event)
    await db.commit()
    await db.refresh(game)

    warnings = []
    if body.games_scouted is not None and body.games_scouted < 3:
        warnings.append("Fewer than 3 games scouted; data confidence is reduced (Gate 1).")
    if (body.camera_quality or "").lower() == "poor":
        warnings.append("Poor camera quality: every individual technique grade drops one tier (flagged ESTIMATE).")
    warnings.append(
        "Draft created. A second, review-authorized user (head coach / coordinator / reviewer / owner) "
        "must sign off via /scout/review before the report can be FINAL (Gate 2)."
    )

    return {"session_id": str(game.id), "opponent": game.opponent, "sport": "basketball",
            "analyst": user.name, "status": "draft", "warnings": warnings}


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


class FreeThrowEntry(BaseModel):
    jersey_number: str                           # the shooter
    attempts: int = 2
    makes: int = 0
    pressure_situation: bool = False             # final 2 min / close game
    shooter_tempo: Optional[str] = None          # quick|routine|slow (strategic-foul timing)
    box_out_formation_offense: Optional[str] = None
    box_out_formation_defense: Optional[str] = None
    quarter: Optional[int] = None
    game_number: Optional[int] = None


class SpecialSituationEntry(BaseModel):
    situation_type: str                          # BLOB|SLOB|press_break|last_second|end_of_quarter
    formation: Optional[str] = None
    primary_action: Optional[str] = None
    target: Optional[str] = None                 # primary target jersey
    result: Optional[str] = None                 # made|missed|reset|turnover
    late_and_close: bool = False                 # final 30s within 3 (highest-trust set)
    quarter: Optional[int] = None
    game_number: Optional[int] = None
    notes: Optional[str] = None


class PlayerProfileEntry(BaseModel):
    """Module-5 analyst grade card. Free-form 1-5 grade fields are tolerated so the
    guard/forward/big card schemas can all flow through one endpoint."""
    jersey: str
    position: Optional[str] = None
    handedness: Optional[str] = None             # left|right|ambidextrous
    role: Optional[str] = None
    visible_examples: int = 0                    # clean single-camera looks (Gate 5)

    class Config:
        extra = "allow"                          # tolerate any 1-5 grade field


class ManualEntry(BaseModel):
    session_id: str
    players: List[PlayerStat] = []
    shots: List[ShotEntry] = []
    turnovers: List[TurnoverEntry] = []
    deflections: List[DeflectionEntry] = []
    possessions: List[PossessionEntry] = []
    free_throws: List[FreeThrowEntry] = []
    special_situations: List[SpecialSituationEntry] = []
    player_profiles: List[PlayerProfileEntry] = []
    replace: bool = False                        # wipe prior events for this session first


def _player_stat_event(org_id, game_id, p: PlayerStat) -> Event:
    return Event(
        organization_id=org_id,
        game_id=game_id,
        event_type="player_stat",
        side="offense",
        player=str(p.jersey_number),
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
    game = await _authorized_session(db, body.session_id, user, write=True)

    if body.replace:
        # Wipe prior DATA events but keep the scout_meta intake (Module 1) intact.
        existing = await db.execute(
            select(Event).where(Event.game_id == game.id, Event.event_type != "scout_meta")
        )
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
            player=str(s.jersey_number),
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
            player=str(t.jersey_number),
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
            player=str(d.jersey_number),
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
            player=str(pos.jersey_number) if pos.jersey_number else None,
            extra_data={
                "primary_player_jersey": str(pos.jersey_number) if pos.jersey_number else None,
                "possession_seconds": pos.possession_seconds,
                "possession_origin": pos.possession_origin,
                "score_diff_at_start": pos.score_diff_at_start,
                "quarter": pos.quarter,
            },
        ))

    for ft in body.free_throws:
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="free_throw",
            side="offense",
            result="made" if ft.makes >= ft.attempts and ft.attempts else None,
            player=str(ft.jersey_number),
            extra_data={
                "primary_player_jersey": str(ft.jersey_number),
                "shooter": str(ft.jersey_number),
                "attempts": ft.attempts,
                "makes": ft.makes,
                "pressure_situation": ft.pressure_situation,
                "shooter_tempo": ft.shooter_tempo,
                "box_out_formation_offense": ft.box_out_formation_offense,
                "box_out_formation_defense": ft.box_out_formation_defense,
                "quarter": ft.quarter,
                "game_number": ft.game_number,
            },
        ))

    for ss in body.special_situations:
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="special_situation",
            side="offense",
            result=ss.result,
            player=str(ss.target) if ss.target else None,
            extra_data={
                "situation_type": ss.situation_type,
                "formation": ss.formation,
                "primary_action": ss.primary_action,
                "target": ss.target,
                "result": ss.result,
                "late_and_close": ss.late_and_close,
                "quarter": ss.quarter,
                "game_number": ss.game_number,
                "notes": ss.notes,
            },
        ))

    for pp in body.player_profiles:
        # side='meta' so the tendency engine ignores it; the coordinator layer
        # reads it as a Module-5 grade card and runs the Gate 5 visibility audit.
        objs.append(Event(
            organization_id=user.organization_id,
            game_id=game.id,
            event_type="player_profile",
            side="meta",
            player=str(pp.jersey),
            extra_data={**pp.model_dump(), "primary_player_jersey": str(pp.jersey)},
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
            "free_throws": len(body.free_throws),
            "special_situations": len(body.special_situations),
            "player_profiles": len(body.player_profiles),
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
    game = await _authorized_session(db, body.session_id, user, write=True)

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
        # Wipe prior DATA events but keep the scout_meta intake (Module 1) intact.
        existing = await db.execute(
            select(Event).where(Event.game_id == game.id, Event.event_type != "scout_meta")
        )
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
    game = await _authorized_session(db, body.session_id, user, write=True)

    # Count only real DATA events — a session with just its scout_meta intake and
    # no logged possessions is not analyzable yet.
    count = await db.execute(
        select(Event).where(Event.game_id == game.id, Event.event_type != "scout_meta")
    )
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


# ── parallel structured retrieval — six categories + full coordinator layer ───
@router.get("/{session_id}/analysis")
async def scouting_analysis(
    session_id: str,
    category: Optional[str] = None,   # optional: return just one of the six categories
    block: Optional[str] = None,      # optional: one coordinator block (gates|game_plan|...)
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The parallel, self-describing scouting view, computed fresh from this
    session's events. Two axes of retrieval:

      • ?category=turnovers  — one of the six priority categories on its own
      • ?block=game_plan     — one coordinator block on its own: gates, game_plan,
        situational, advanced, late_game, free_throws, special_situations,
        player_profiles, camera_confidence

    Every payload echoes sport + opponent, so there is no chance of confusing one
    sport's data with another's, or one category/block with another. Distinct from
    /analyze, which queues the combined coach-facing prose report.
    """
    game = await _authorized_session(db, session_id, user, write=False)

    ev_result = await db.execute(select(Event).where(Event.game_id == game.id))
    events = ev_result.scalars().all()

    # Run the full engine so `scouting` carries the six categories AND the
    # coordinator layer (validation gates, game plan, advanced metrics, etc.).
    summary = await run_tendency_engine("basketball", events)
    scouting = summary.get("scouting", {}) or {}

    categories = [
        {"priority": pri, "key": key, "name": name, "data": scouting.get(engine_key, {})}
        for (pri, key, name, engine_key) in SCOUT_CATEGORIES
    ]
    if category:
        match = next((c for c in categories if c["key"] == category), None)
        if not match:
            valid = ", ".join(c["key"] for c in categories)
            raise HTTPException(status_code=404, detail=f"Unknown category '{category}'. Valid: {valid}")
        categories = [match]

    coordinator_blocks = {
        "gates": {
            "report_status": scouting.get("report_status"),
            "validation_gates": scouting.get("validation_gates", []),
        },
        "game_plan": {
            "game_plan": scouting.get("game_plan", {}),
            "game_plan_priorities": scouting.get("game_plan_priorities", []),
            "head_coach_priorities": scouting.get("head_coach_priorities", []),
        },
        "situational": scouting.get("situational_tendencies", []),
        "advanced": scouting.get("advanced_metrics", {}),
        "late_game": scouting.get("late_game_profile", {}),
        "free_throws": scouting.get("free_throw_profile", {}),
        "special_situations": scouting.get("special_situations", {}),
        "player_profiles": scouting.get("player_profiles", {}),
        "camera_confidence": scouting.get("camera_confidence", {}),
    }
    if block:
        if block not in coordinator_blocks:
            raise HTTPException(status_code=404,
                                detail=f"Unknown block '{block}'. Valid: {', '.join(coordinator_blocks)}")
        coordinator_blocks = {block: coordinator_blocks[block]}

    return {
        "session_id": str(game.id),
        "sport": game.sport,                 # always the discriminator, echoed back
        "opponent": game.opponent,
        "report_status": scouting.get("report_status", "PRELIMINARY"),
        "total_events": len(events),
        "total_possessions": scouting.get("total_possessions", 0),
        "games_scouted": scouting.get("games_scouted", 1),
        "personnel_flagged": scouting.get("personnel_flagged", False),
        "available": scouting.get("available", False),
        "categories": categories,            # the six, in parallel, priority-ordered
        "coordinator": coordinator_blocks,   # gates, game plan, advanced, late-game, ...
    }


# ── dual-analyst review sign-off (Gate 2 teeth) ──────────────────────────────
class ReviewRequest(BaseModel):
    session_id: str
    decision: str = "reviewed"                     # "reviewed" | "final" | "changes_requested"
    notes: Optional[str] = None
    disputed_tendencies: Optional[List[str]] = None


@router.post("/review")
async def review_session(
    body: ReviewRequest,
    user: User = Depends(require_scout_reviewer),   # must hold review authority
    db: AsyncSession = Depends(get_db),
):
    """Second-analyst sign-off. This is what makes Gate 2 real: only an
    authenticated, review-authorized user who is NOT the primary analyst can
    advance a session to reviewed/final. Identity is the token, not a form field.
    """
    game = await _load_session(db, body.session_id, user.organization_id)
    meta = await _load_meta_event(db, game.id)
    if not meta:
        raise HTTPException(status_code=422, detail="Session has no intake metadata to review.")

    data = dict(meta.extra_data or {})
    analyst_id = data.get("analyst_id")
    if analyst_id and str(analyst_id) == str(user.id):
        raise HTTPException(
            status_code=403,
            detail="You are the primary analyst on this session. Dual review requires a different reviewer.",
        )

    decision = (body.decision or "reviewed").lower()
    if decision not in ("reviewed", "final", "changes_requested"):
        raise HTTPException(status_code=422, detail="decision must be reviewed, final, or changes_requested")

    if decision == "changes_requested":
        data["status"] = "draft"
    else:
        data["reviewer_id"] = str(user.id)
        data["reviewer"] = user.name
        data["status"] = decision
    data["review_notes"] = body.notes
    data["disputed_tendencies"] = body.disputed_tendencies or []
    meta.extra_data = data
    # JSONB in-place mutation needs an explicit flag for SQLAlchemy to persist it.
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(meta, "extra_data")
    await db.commit()

    await log_agent_action(
        action="scout_review_signoff",
        game_id=str(game.id),
        organization_id=str(user.organization_id),
        phase="scout",
        reason=f"{user.name} ({user.role}) set review status to '{data['status']}' on {game.opponent} scout.",
        level="success",
        detail={"reviewer_id": str(user.id), "decision": decision,
                "disputed": len(body.disputed_tendencies or [])},
    )
    return {"session_id": str(game.id), "status": data["status"],
            "reviewer": user.name, "gate2_passed": data["status"] in ("reviewed", "final")}


# ── sessions list (RLS: analysts see own, reviewers see the whole org) ────────
@router.get("/sessions")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Game).where(Game.organization_id == user.organization_id,
                           Game.sport == "basketball", Game.status == "manual")
        .order_by(Game.created_at.desc()).limit(200)
    )
    games = result.scalars().all()
    reviewer = can_review_scout(user)

    out = []
    for g in games:
        meta = await _load_meta_event(db, g.id)
        data = (meta.extra_data if meta else {}) or {}
        analyst_id = data.get("analyst_id")
        # RLS: a plain analyst only sees sessions they own; reviewers see all.
        if not reviewer and analyst_id and str(analyst_id) != str(user.id):
            continue
        out.append({
            "session_id": str(g.id),
            "opponent": g.opponent,
            "game_date": g.game_date.isoformat() if g.game_date else None,
            "analyst": data.get("analyst"),
            "reviewer": data.get("reviewer"),
            "status": data.get("status", "draft"),
            "camera_quality": data.get("camera_quality"),
            "is_mine": analyst_id is not None and str(analyst_id) == str(user.id),
            "can_review": reviewer and (not analyst_id or str(analyst_id) != str(user.id)),
        })
    return {"sessions": out, "you_can_review": reviewer}
