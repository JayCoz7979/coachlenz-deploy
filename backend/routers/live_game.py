"""
Live Game Play Logger — real-time, sideline play-by-play charting for a live game,
with a halftime and a full-game report generated from the logged plays.

Unlike the opponent scout (scout_football / scout), a live game logs YOUR OWN team:
when you have the ball those are your offensive plays, when they have it those are
your defensive plays, and special teams are their own unit. So the side mapping is:

    possession = us   -> side = "offense"          (our offense)
    possession = them -> side = "defense"           (our defense; the opponent's
                                                     offensive detail rides in extra_data)
    special teams     -> side = "special_teams"

This lands every play in the same shared ``events`` table the film auto-detection and
the scout logger already use, so ONE tendency engine and ONE report pipeline serve the
live logger too — no new play tables. Setup config + both rosters are stashed on a
single ``game_meta`` event (side='meta'), mirroring the proven scout_meta pattern; the
tendency engine ignores non-play (meta) events.

The halftime report is a self-scout report (report_type='self_scout') scoped to
first-half plays via ``TendencyReport.params.event_filter`` (migration 037). The
full-game report is the same, unscoped.

Endpoints (prefix /live):
    POST   /session                 create a live game session (setup + rosters)
    GET    /sessions                list this org's live game sessions
    GET    /session/{id}            session config + all logged plays (resume/review)
    POST   /plays                   append a batch of logged plays
    PATCH  /play/{event_id}         edit one logged play
    DELETE /play/{event_id}         delete one logged play
    POST   /play/{event_id}/flag    toggle a play as a Coaching Point (+ optional note)
    POST   /report                  queue a halftime or full-game report
"""
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.models.event import Event
from backend.models.job import Job
from backend.models.report import TendencyReport
from backend.services.auth import get_current_user, get_current_org
from backend.services.agent_log import log_agent_action
from backend.services.sports import assert_sport_allowed
from backend.services.legal import assert_student_consent

router = APIRouter(prefix="/live", tags=["live-game"])

# The three sports the live logger supports (mirrors the flag football / football /
# basketball tendency engines that already exist).
LIVE_SPORTS = {"football", "flag_football", "basketball"}
# Event.side values the tendency engine splits on.
VALID_SIDES = {"offense", "defense", "special_teams"}
# The single meta event holds setup + rosters and is ignored by the engine.
META_EVENT_TYPE = "game_meta"

# Fields that are not first-class Event columns ride in extra_data. This is the
# full sport-specific vocabulary the logger UI produces; we persist whatever is
# present and let the report writer / tendency engine read what it understands.
_EXTRA_KEYS = (
    # shared situational
    "quarter", "half", "play_number", "possession", "time_clock",
    "score_us", "score_them", "late_game",
    # football / flag offense
    "passer_jersey", "ball_carrier_jersey", "target_jersey", "run_category",
    "run_gap", "run_gap_label", "route", "rush_lane", "rush_type", "pass_result",
    "custom_route",
    # football / flag defense (ours) + opponent detail
    "defensive_front", "opp_formation", "opp_play_type", "opp_ball_carrier",
    "opp_target", "opp_run_gap", "opp_route", "stop_maker_jersey", "pass_rush",
    # special teams
    "st_unit", "kicker_jersey", "returner_jersey", "st_result", "st_yards",
    # basketball offense
    "ball_handler_jersey", "ball_entry", "primary_action", "shooter_jersey",
    "shot_zone", "shot_result", "turnover_type", "turnover_jersey",
    "offensive_rebound", "second_chance", "foul_drawn_jersey", "possession_result",
    # basketball defense (ours) + opponent detail
    "defensive_set", "pressure_applied", "help_defense", "opp_ball_handler",
    "opp_primary_action", "opp_shooter", "shot_zone_allowed", "fouled_by_jersey",
    "defensive_rebound",
    # basketball special situations
    "special_situation", "set_play_name", "intended_outcome",
    # logging metadata
    "penalty_type", "penalty_on", "penalty_jersey", "is_quick_log",
)


# ── helpers ──────────────────────────────────────────────────────────────────
async def _load_session(db: AsyncSession, session_id: str, org_id) -> Game:
    result = await db.execute(
        select(Game).where(
            Game.id == session_id,
            Game.organization_id == org_id,
            Game.status == "live",
        )
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Live game session not found")
    return game


async def _meta_event(db: AsyncSession, game_id) -> Optional[Event]:
    result = await db.execute(
        select(Event).where(Event.game_id == game_id, Event.event_type == META_EVENT_TYPE)
    )
    return result.scalar_one_or_none()


async def _load_play(db: AsyncSession, event_id: str, org_id) -> Event:
    result = await db.execute(
        select(Event).where(
            Event.id == event_id,
            Event.organization_id == org_id,
            Event.event_type == "play",
        )
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Logged play not found")
    return ev


def _side_from_possession(possession: Optional[str], explicit_side: Optional[str],
                          play_type: Optional[str]) -> str:
    """Resolve the Event.side the tendency engine splits on.

    Special teams always wins. Otherwise possession decides: we log our own team,
    so 'us' -> our offense, 'them' -> our defense. An explicit valid side overrides.
    """
    if explicit_side in VALID_SIDES:
        return explicit_side
    if (play_type or "").lower() in ("special_teams", "special", "st"):
        return "special_teams"
    p = (possession or "us").lower()
    return "defense" if p in ("them", "opp", "opponent", "defense") else "offense"


# ── models ───────────────────────────────────────────────────────────────────
class RosterEntry(BaseModel):
    jersey: str
    name: Optional[str] = None


class SessionCreate(BaseModel):
    sport: str
    team_name: str
    opponent: str
    game_date: Optional[str] = None          # ISO YYYY-MM-DD
    location: Optional[str] = None
    is_home: Optional[bool] = None
    game_type: Optional[str] = None          # regular_season | playoff | scrimmage
    team_id: Optional[str] = None

    # football / flag football setup
    weather: Optional[str] = None            # clear | overcast | rain | wind | cold
    field_surface: Optional[str] = None      # grass | turf
    starting_possession: Optional[str] = None
    terminology_system: Optional[str] = None  # gap_letters | hole_numbers | zones
    custom_routes: Optional[List[str]] = None
    league_format: Optional[str] = None      # flag football: 5on5 | 7on7 | 8on8

    # optional pre-loaded rosters (jersey + optional name)
    our_roster: Optional[List[RosterEntry]] = None
    opponent_roster: Optional[List[RosterEntry]] = None


class PlayEntry(BaseModel):
    possession: Optional[str] = "us"         # us | them
    side: Optional[str] = None               # offense | defense | special_teams (override)
    quarter: Optional[int] = None
    half: Optional[int] = None
    play_number: Optional[int] = None
    time_clock: Optional[str] = None
    time_seconds: Optional[float] = None

    # first-class Event columns
    down: Optional[int] = None
    distance: Optional[int] = None
    field_position: Optional[str] = None
    formation: Optional[str] = None
    personnel: Optional[str] = None
    play_type: Optional[str] = None
    result: Optional[str] = None
    yards_gained: Optional[int] = None
    coverage: Optional[str] = None
    blitz: Optional[str] = None
    motion: Optional[bool] = False
    primary_player_jersey: Optional[str] = None    # -> Event.player (BC/shooter/target)

    is_coaching_point: Optional[bool] = False
    note: Optional[str] = None

    class Config:
        extra = "allow"                       # tolerate any extra sport-specific tag


class PlaysBatch(BaseModel):
    session_id: str
    plays: List[PlayEntry] = []


class PlayEdit(BaseModel):
    down: Optional[int] = None
    distance: Optional[int] = None
    field_position: Optional[str] = None
    formation: Optional[str] = None
    play_type: Optional[str] = None
    result: Optional[str] = None
    yards_gained: Optional[int] = None
    coverage: Optional[str] = None
    blitz: Optional[str] = None
    primary_player_jersey: Optional[str] = None
    note: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None    # merge into extra_data (sport fields)


class FlagRequest(BaseModel):
    is_coaching_point: bool = True
    note: Optional[str] = None


class ReportRequest(BaseModel):
    session_id: str
    scope: str = "full"                       # halftime | full
    title: Optional[str] = None


def _play_to_event(org_id, game_id, p: PlayEntry) -> Event:
    side = _side_from_possession(p.possession, p.side, p.play_type)
    extra: Dict[str, Any] = {}
    # Anything in _EXTRA_KEYS (incl. any extra="allow" sport tags) rides in extra_data.
    data = p.model_dump(exclude_none=True)
    for k in _EXTRA_KEYS:
        if k in data and data[k] is not None:
            extra[k] = data[k]
    # possession is always useful for the review view even if 'us'
    extra.setdefault("possession", (p.possession or "us"))
    return Event(
        organization_id=org_id,
        game_id=game_id,
        event_type="play",
        side=side,
        time_seconds=p.time_seconds,
        down=p.down,
        distance=p.distance,
        field_position=p.field_position,
        formation=p.formation,
        personnel=p.personnel,
        play_type=p.play_type,
        result=p.result,
        yards_gained=p.yards_gained,
        coverage=p.coverage,
        blitz=p.blitz,
        motion=bool(p.motion),
        player=str(p.primary_player_jersey) if p.primary_player_jersey else None,
        is_highlight=bool(p.is_coaching_point),
        coach_note=(p.note or None),
        extra_data={k: v for k, v in extra.items() if v is not None},
    )


def _event_to_play(e: Event) -> Dict[str, Any]:
    extra = e.extra_data or {}
    return {
        "event_id": str(e.id),
        "side": e.side,
        "possession": extra.get("possession"),
        "quarter": extra.get("quarter"),
        "half": extra.get("half"),
        "play_number": extra.get("play_number"),
        "down": e.down,
        "distance": e.distance,
        "field_position": e.field_position,
        "formation": e.formation,
        "play_type": e.play_type,
        "result": e.result,
        "yards_gained": e.yards_gained,
        "coverage": e.coverage,
        "player": e.player,
        "is_coaching_point": bool(e.is_highlight),
        "note": e.coach_note,
        "is_quick_log": bool(extra.get("is_quick_log")),
        "extra": extra,
    }


# ── session intake ───────────────────────────────────────────────────────────
@router.post("/session")
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    sport = (body.sport or "").lower()
    if sport not in LIVE_SPORTS:
        raise HTTPException(status_code=422,
                            detail=f"sport must be one of: {', '.join(sorted(LIVE_SPORTS))}")
    assert_sport_allowed(org, sport)
    # COPPA/FERPA: a live game logs student-athletes by jersey (individual
    # identifiers), so require the student-data authority attestation first —
    # same gate as roster, film, and scout.
    await assert_student_consent(db, org.id)

    gd = None
    if body.game_date:
        try:
            gd = date.fromisoformat(body.game_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="game_date must be ISO format YYYY-MM-DD")

    game = Game(
        organization_id=org.id,
        team_id=body.team_id,
        title=f"{body.team_name} vs {body.opponent}",
        sport=sport,
        opponent=body.opponent,
        game_date=gd,
        is_home=body.is_home,
        status="live",
        is_trial_game=getattr(org, "is_trial", False),
    )
    db.add(game)
    await db.flush()

    meta = Event(
        organization_id=org.id,
        game_id=game.id,
        event_type=META_EVENT_TYPE,
        side="meta",
        extra_data={
            "sport": sport,
            "team_name": body.team_name,
            "opponent": body.opponent,
            "location": body.location,
            "is_home": body.is_home,
            "game_type": body.game_type,
            "weather": body.weather,
            "field_surface": body.field_surface,
            "starting_possession": body.starting_possession,
            "terminology_system": body.terminology_system or "gap_letters",
            "custom_routes": body.custom_routes or [],
            "league_format": body.league_format,
            "our_roster": [r.model_dump() for r in (body.our_roster or [])],
            "opponent_roster": [r.model_dump() for r in (body.opponent_roster or [])],
            "created_by": str(user.id),
            "created_by_name": user.name,
        },
    )
    db.add(meta)
    await db.commit()
    await db.refresh(game)

    await log_agent_action(
        action="create_live_game_session",
        game_id=str(game.id),
        organization_id=str(org.id),
        phase="live_logger",
        reason=f"Live game session started: {body.team_name} vs {body.opponent} ({sport}).",
        level="info",
        detail={"sport": sport, "opponent": body.opponent},
    )
    return {"session_id": str(game.id), "sport": sport,
            "team_name": body.team_name, "opponent": game.opponent, "status": "live"}


@router.get("/sessions")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Game).where(Game.organization_id == user.organization_id, Game.status == "live")
        .order_by(Game.created_at.desc()).limit(200)
    )
    games = result.scalars().all()
    out = []
    for g in games:
        meta = await _meta_event(db, g.id)
        data = (meta.extra_data if meta else {}) or {}
        # cheap play count
        cnt = await db.execute(
            select(Event).where(Event.game_id == g.id, Event.event_type == "play")
        )
        out.append({
            "session_id": str(g.id),
            "sport": g.sport,
            "team_name": data.get("team_name"),
            "opponent": g.opponent,
            "game_date": g.game_date.isoformat() if g.game_date else None,
            "game_type": data.get("game_type"),
            "play_count": len(cnt.scalars().all()),
            "created_at": g.created_at.isoformat() if g.created_at else None,
        })
    return {"sessions": out}


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, session_id, user.organization_id)
    meta = await _meta_event(db, game.id)
    plays_result = await db.execute(
        select(Event).where(Event.game_id == game.id, Event.event_type == "play")
        .order_by(Event.created_at.asc())
    )
    plays = [_event_to_play(e) for e in plays_result.scalars().all()]
    return {
        "session_id": str(game.id),
        "sport": game.sport,
        "opponent": game.opponent,
        "status": game.status,
        "config": (meta.extra_data if meta else {}) or {},
        "plays": plays,
    }


# ── logging ──────────────────────────────────────────────────────────────────
@router.post("/plays")
async def add_plays(
    body: PlaysBatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, body.session_id, user.organization_id)
    objs = [_play_to_event(user.organization_id, game.id, p) for p in body.plays]
    db.add_all(objs)
    await db.commit()
    for o in objs:
        await db.refresh(o)

    # On-the-fly jersey numbers auto-join the session roster (spec: setup rosters).
    await _absorb_new_jerseys(db, game, body.plays)

    by_side: Dict[str, int] = {}
    for o in objs:
        by_side[o.side] = by_side.get(o.side, 0) + 1
    return {"session_id": str(game.id), "plays_written": len(objs),
            "by_side": by_side, "event_ids": [str(o.id) for o in objs]}


async def _absorb_new_jerseys(db: AsyncSession, game: Game, plays: List[PlayEntry]) -> None:
    """Save jersey numbers entered on the fly to the session roster (our side)."""
    meta = await _meta_event(db, game.id)
    if not meta:
        return
    data = dict(meta.extra_data or {})
    roster = data.get("our_roster") or []
    known = {str(r.get("jersey")) for r in roster}
    added = False
    for p in plays:
        j = p.primary_player_jersey
        if j and str(j) not in known and (p.possession or "us").lower() in ("us", "offense"):
            roster.append({"jersey": str(j), "name": None})
            known.add(str(j))
            added = True
    if added:
        data["our_roster"] = roster
        meta.extra_data = data
        flag_modified(meta, "extra_data")
        await db.commit()


@router.patch("/play/{event_id}")
async def edit_play(
    event_id: str,
    body: PlayEdit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = await _load_play(db, event_id, user.organization_id)
    data = body.model_dump(exclude_unset=True)
    col_map = {
        "down": "down", "distance": "distance", "field_position": "field_position",
        "formation": "formation", "play_type": "play_type", "result": "result",
        "yards_gained": "yards_gained", "coverage": "coverage", "blitz": "blitz",
    }
    for field, col in col_map.items():
        if field in data:
            setattr(ev, col, data[field])
    if "primary_player_jersey" in data:
        ev.player = str(data["primary_player_jersey"]) if data["primary_player_jersey"] else None
    if "note" in data:
        ev.coach_note = data["note"] or None
    if data.get("extra"):
        merged = dict(ev.extra_data or {})
        merged.update({k: v for k, v in data["extra"].items() if v is not None})
        ev.extra_data = merged
        flag_modified(ev, "extra_data")
    await db.commit()
    await db.refresh(ev)
    return {"event_id": str(ev.id), "play": _event_to_play(ev)}


@router.delete("/play/{event_id}")
async def delete_play(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ev = await _load_play(db, event_id, user.organization_id)
    await db.delete(ev)
    await db.commit()
    return {"deleted": event_id}


@router.post("/play/{event_id}/flag")
async def flag_play(
    event_id: str,
    body: FlagRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flag/unflag a play as a Coaching Point. is_highlight is what the report's
    coach-notes digest reads, so a flagged play surfaces in the halftime report."""
    ev = await _load_play(db, event_id, user.organization_id)
    ev.is_highlight = bool(body.is_coaching_point)
    if body.note is not None:
        ev.coach_note = body.note or None
    await db.commit()
    return {"event_id": str(ev.id), "is_coaching_point": ev.is_highlight, "note": ev.coach_note}


# ── report ───────────────────────────────────────────────────────────────────
@router.post("/report")
async def generate_report(
    body: ReportRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_session(db, body.session_id, user.organization_id)
    scope = (body.scope or "full").lower()
    if scope not in ("halftime", "full"):
        raise HTTPException(status_code=422, detail="scope must be 'halftime' or 'full'")

    ev = await db.execute(
        select(Event).where(Event.game_id == game.id, Event.event_type == "play")
    )
    plays = ev.scalars().all()
    if not plays:
        raise HTTPException(status_code=422,
                            detail="No plays logged yet. Log at least one play before generating a report.")

    # Halftime scoping: first half only. Basketball uses 'half', football/flag 'quarter'.
    params = None
    if scope == "halftime":
        if game.sport == "basketball":
            params = {"event_filter": {"max_half": 1}}
        else:
            params = {"event_filter": {"max_quarter": 2}}

    meta = await _meta_event(db, game.id)
    team_name = ((meta.extra_data if meta else {}) or {}).get("team_name") or "Us"
    label = "Halftime" if scope == "halftime" else "Full Game"
    report = TendencyReport(
        organization_id=org.id,
        team_id=game.team_id,
        game_ids=[str(game.id)],
        sport=game.sport,
        report_type="self_scout",              # an "us"-oriented report (our tendencies)
        title=body.title or f"{label} Report: {team_name} vs {game.opponent or 'Opponent'}",
        params=params,
        is_trial=getattr(org, "is_trial", False),
        watermarked=getattr(org, "is_trial", False),
    )
    db.add(report)
    await db.flush()
    job = Job(organization_id=org.id, job_type="report", payload={"report_id": str(report.id)})
    db.add(job)
    await db.commit()

    await log_agent_action(
        action="queue_live_game_report",
        game_id=str(game.id),
        organization_id=str(org.id),
        job_id=str(job.id),
        phase="live_logger",
        reason=f"{label} report queued from {len(plays)} logged plays.",
        level="info",
        detail={"report_id": str(report.id), "scope": scope, "plays": len(plays)},
    )
    return {"report_id": str(report.id), "session_id": str(game.id),
            "scope": scope, "status": "queued", "plays": len(plays)}
