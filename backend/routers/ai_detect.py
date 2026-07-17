from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, and_, or_
from datetime import datetime, timedelta
from backend.models.base import get_db
from backend.models.user import User
from backend.models.game import Game
from backend.models.job import Job
from backend.models.event import Event
from backend.models.agent_log import AgentLog
from backend.services.auth import get_current_user
from backend.utils.timeutils import to_naive_utc

router = APIRouter(prefix="/games", tags=["ai-detect"])

ACCURACY_MATCH_WINDOW_S = 15  # a predicted play within this many seconds of a truth play is a "match"


def _is_ai(e) -> bool:
    return bool((e.extra_data or {}).get("auto_detected"))


def _norm(v) -> str:
    return ("" if v is None else str(v)).strip().lower()


@router.get("/{game_id}/accuracy")
async def accuracy_benchmark(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Measure AI detection accuracy against coach-verified (manual) plays.

    Ground truth = manually tagged plays. Prediction = AI auto-detected plays.
    Returns recall, precision, and per-attribute agreement on matched plays.
    """
    res = await db.execute(
        select(Event).where(Event.game_id == game_id, Event.organization_id == user.organization_id)
    )
    events = res.scalars().all()
    truth = sorted([e for e in events if not _is_ai(e)], key=lambda e: e.time_seconds or 0)
    pred = sorted([e for e in events if _is_ai(e)], key=lambda e: e.time_seconds or 0)

    if not truth:
        return {
            "ready": False,
            "reason": "No coach-verified plays yet. Manually tag this game (ground truth), then run AI auto-detect, then check accuracy.",
            "truth_plays": 0, "ai_plays": len(pred),
        }
    if not pred:
        return {
            "ready": False,
            "reason": "No AI-detected plays yet. Run AI auto-detect on this game, then check accuracy.",
            "truth_plays": len(truth), "ai_plays": 0,
        }

    # Scope to the time span the coach actually tagged, so tagging a representative
    # slice (e.g. one quarter) is judged fairly instead of being punished for the AI
    # plays elsewhere in the game.
    tmin = min((t.time_seconds or 0) for t in truth)
    tmax = max((t.time_seconds or 0) for t in truth)
    w_lo, w_hi = tmin - ACCURACY_MATCH_WINDOW_S, tmax + ACCURACY_MATCH_WINDOW_S
    pred_window = [p for p in pred if w_lo <= (p.time_seconds or 0) <= w_hi]
    scoped = len(pred_window) < len(pred)

    # Greedy nearest-in-time matching, one prediction per truth play.
    used = set()
    matches = []
    for t in truth:
        best_i, best_d = None, ACCURACY_MATCH_WINDOW_S + 1
        for i, p in enumerate(pred_window):
            if i in used:
                continue
            d = abs((p.time_seconds or 0) - (t.time_seconds or 0))
            if d <= ACCURACY_MATCH_WINDOW_S and d < best_d:
                best_i, best_d = i, d
        if best_i is not None:
            used.add(best_i)
            matches.append((t, pred_window[best_i]))

    recall = len(matches) / len(truth) if truth else 0
    precision = len(matches) / len(pred_window) if pred_window else 0
    missed = len(truth) - len(matches)            # real plays the AI did not catch
    false_pos = len(pred_window) - len(matches)   # AI plays that matched no real play

    # Per-attribute agreement on matched pairs (only where the truth has a value).
    fields = ["side", "play_type", "down", "distance", "formation", "defensive_front", "coverage", "result"]
    attr = {}
    for f in fields:
        agree = total = 0
        for t, p in matches:
            tv = getattr(t, f, None)
            if tv is None or tv == "":
                continue
            total += 1
            if _norm(tv) == _norm(getattr(p, f, None)):
                agree += 1
        attr[f] = {"agree": agree, "total": total, "pct": round(agree / total * 100, 1) if total else None}

    return {
        "ready": True,
        "truth_plays": len(truth),
        "ai_plays": len(pred_window),
        "ai_plays_total": len(pred),
        "matched": len(matches),
        "missed": missed,
        "false_positives": false_pos,
        "recall_pct": round(recall * 100, 1),       # of real plays, how many AI caught
        "precision_pct": round(precision * 100, 1),  # of AI plays (in window), how many were real
        "match_window_s": ACCURACY_MATCH_WINDOW_S,
        "scoped_to_tags": scoped,
        "window": {"start": int(tmin), "end": int(tmax)},
        "attribute_accuracy": attr,
    }


# Fields whose fill rate we score, and whether they live on the column or in extra_data.
_COVERAGE_FIELDS = [
    ("down", False), ("distance", False), ("formation", False), ("play_type", False),
    ("result", False), ("field_position", False), ("personnel", False),
    ("coverage", False), ("defensive_front", False),
]


@router.post("/{game_id}/rederive-downs")
async def rederive_downs(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Propagate down & distance across each drive from the anchors already present
    (coach tags or AI reads), filling in the gaps. Only fills missing values."""
    from backend.services.derive_downs import fill_down_distance

    res = await db.execute(
        select(Event)
        .where(Event.game_id == game_id, Event.organization_id == user.organization_id)
        .order_by(Event.time_seconds.asc())
    )
    events = list(res.scalars().all())
    if not events:
        raise HTTPException(status_code=404, detail="No plays on this game yet")

    rows = [{
        "side": e.side, "down": e.down, "distance": e.distance,
        "yards_gained": e.yards_gained,
    } for e in events]

    filled = fill_down_distance(rows)

    # Write the filled values back to the events.
    for e, r in zip(events, rows):
        if e.down is None and r.get("down") is not None:
            e.down = r["down"]
        if e.distance is None and r.get("distance") is not None:
            e.distance = r["distance"]
    await db.commit()

    with_dd = sum(1 for e in events if e.down is not None and e.distance is not None)
    return {
        "ok": True,
        "fields_filled": filled,
        "plays": len(events),
        "plays_with_down_distance": with_dd,
        "down_distance_coverage_pct": round(with_dd / len(events) * 100, 1),
    }


@router.get("/{game_id}/tendencies")
async def game_tendencies(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The full structured tendency breakdown of a game's plays. Deterministic
    (no AI / no API spend) — lets a coach see run/pass, formation, down-and-distance
    and situational tendencies directly from the detected plays."""
    from backend.services.tendency_engine.engine import run_tendency_engine

    game = (await db.execute(
        select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id)
    )).scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    res = await db.execute(
        select(Event).where(Event.game_id == game_id, Event.organization_id == user.organization_id)
    )
    events = list(res.scalars().all())
    if not events:
        return {"ready": False, "reason": "No plays yet. Break down the film first."}

    sport = (game.sport or "football").lower()
    data = await run_tendency_engine(sport, events)
    # Flag the team-attribution caveat so the UI can warn honestly.
    team_set = bool((game.scout_jersey or "").strip())
    return {"ready": True, "sport": sport, "team_colors_set": team_set,
            "opponent": game.opponent, "title": game.title, **data}


@router.get("/{game_id}/coverage")
async def coverage_scorecard(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Instant detection scorecard, no manual tagging required. Reports how complete
    the AI reads are (fill rate per field) and how confident (confident vs flagged),
    so a coach can judge a game's data quality before game-planning around it."""
    res = await db.execute(
        select(Event).where(Event.game_id == game_id, Event.organization_id == user.organization_id)
    )
    events = [e for e in res.scalars().all() if _is_ai(e)]
    n = len(events)
    if not n:
        return {"ready": False, "reason": "No AI-detected plays yet. Run auto-detect first.", "plays": 0}

    def filled(attr, in_extra):
        c = 0
        for e in events:
            v = (e.extra_data or {}).get(attr) if in_extra else getattr(e, attr, None)
            if v not in (None, "", [], {}):
                c += 1
        return round(c / n * 100, 1)

    fill_rates = {attr: filled(attr, in_extra) for attr, in_extra in _COVERAGE_FIELDS}

    confs = [float((e.extra_data or {}).get("confidence") or 0) for e in events]
    avg_conf = round(sum(confs) / n, 2)
    flagged = sum(1 for e in events if (e.extra_data or {}).get("needs_review"))
    confident = n - flagged

    def side_of(e):
        return (e.side or "offense")
    sides = {s: sum(1 for e in events if side_of(e) == s) for s in ("offense", "defense", "special_teams")}

    # Weakest fields surface what to fix first.
    weakest = sorted(fill_rates.items(), key=lambda kv: kv[1])[:3]

    return {
        "ready": True,
        "plays": n,
        "fill_rates": fill_rates,
        "avg_confidence": avg_conf,
        "confident": confident,
        "flagged_for_review": flagged,
        "confident_pct": round(confident / n * 100, 1),
        "side_split": sides,
        "weakest_fields": [k for k, _ in weakest],
    }


@router.post("/{game_id}/auto-detect")
async def trigger_auto_detect(
    game_id: str,
    dry_run: bool = False,
    mode: str = "fast",  # "fast" = 1x single-pass, "deep" = 3x multi-pass engine
    full: bool = False,  # bypass the per-run segment cost guard (analyze every segment)
    test: bool = False,  # quick test: analyze only the opening minutes (pennies)
    grade: bool = False, # opt-in technique-grading pass (OL/DL/QB/tackle/coverage), Opus per-play
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue an AI play-detection job for a game that is already ingested (status=ready).

    dry_run=true runs the UATP staging mode: the agent simulates detection and logs
    what it WOULD save, without writing any plays.
    """
    result = await db.execute(
        select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status not in ("ready", "analyzing"):
        raise HTTPException(
            status_code=400,
            detail=f"Game must be ready before auto-detection (current status: {game.status})",
        )

    # Clean up orphaned jobs: a "running" job whose worker died (e.g. a redeploy)
    # would otherwise block re-runs for 30 min. Mark stale ones errored so a fresh
    # run can proceed and the orphan never double-runs.
    stale_cutoff = datetime.utcnow() - timedelta(minutes=10)
    await db.execute(
        update(Job).where(
            Job.job_type == "ai_detect",
            Job.payload["game_id"].as_string() == game_id,
            Job.status == "running",
            Job.locked_at < stale_cutoff,
        ).values(status="error", error_message="Orphaned (worker restarted); superseded by a new run.")
    )
    await db.commit()

    # Block only if a genuinely active job exists (queued, or running-and-fresh).
    existing = await db.execute(
        select(Job).where(
            Job.job_type == "ai_detect",
            Job.payload["game_id"].as_string() == game_id,
            or_(
                Job.status == "queued",
                and_(Job.status == "running", Job.locked_at >= stale_cutoff),
            ),
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_queued", "game_id": game_id}

    job = Job(
        organization_id=user.organization_id,
        job_type="ai_detect",
        payload={"game_id": game_id, "dry_run": dry_run,
                 "detection_mode": ("deep" if mode == "deep" else "fast"),
                 "full": bool(full), "test": bool(test), "grade": bool(grade)},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {"status": "queued", "job_id": str(job.id), "game_id": game_id, "dry_run": dry_run}


@router.get("/{game_id}/auto-detect/status")
async def detect_status(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll detection progress: returns job status + play count found so far."""
    result = await db.execute(
        select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id)
    )
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Most recent detect job
    job_result = await db.execute(
        select(Job)
        .where(Job.job_type == "ai_detect", Job.payload["game_id"].as_string() == game_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    job = job_result.scalar_one_or_none()

    # Capture ORM values up front: the self-heal commit below expires ORM objects,
    # and reading them afterward triggers a forbidden async lazy-load (500).
    game_status = game.status
    job_status = job.status if job else None
    # The locked_at column comes back timezone-AWARE from Postgres, but stale_cutoff
    # below is a naive utcnow(); comparing the two throws TypeError and 500s the whole
    # status check (which the UI reads as "Could not start the film breakdown").
    # Normalize to naive UTC so the comparison is always valid.
    job_locked_at = to_naive_utc(job.locked_at if job else None)
    job_payload = job.payload if job else None
    job_error = job.error_message if job else None

    # Self-heal a stuck "analyzing" game: if the run that set it is no longer active
    # (errored, done, or orphaned), reset to "ready" so the UI recovers and re-run
    # buttons reappear instead of spinning forever.
    if game_status == "analyzing":
        stale_cutoff = datetime.utcnow() - timedelta(minutes=10)
        active = job is not None and (
            job_status == "queued"
            or (job_status == "running" and job_locked_at is not None and job_locked_at >= stale_cutoff)
        )
        if not active:
            await db.execute(update(Game).where(Game.id == game_id).values(status="ready"))
            await db.commit()
            game_status = "ready"

    # Count auto-detected events
    count_result = await db.execute(
        select(func.count(Event.id)).where(
            Event.game_id == game_id,
            Event.extra_data["auto_detected"].as_boolean() == True,
        )
    )
    auto_count = count_result.scalar() or 0

    # Count plays the agent flagged for human review (UATP escalation surfaced to coach)
    review_result = await db.execute(
        select(func.count(Event.id)).where(
            Event.game_id == game_id,
            Event.extra_data["auto_detected"].as_boolean() == True,
            Event.extra_data["needs_review"].as_boolean() == True,
        )
    )
    needs_review = review_result.scalar() or 0

    return {
        "game_id": game_id,
        "game_status": game_status,
        "job_status": job_status,
        "plays_detected": auto_count,
        "needs_review": needs_review,
        "dry_run": bool((job_payload or {}).get("dry_run")) if job_payload else False,
        "error": job_error if job_status == "error" else None,
    }


@router.get("/{game_id}/players")
async def player_tendencies(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-player tendency tracking for a game (charter Component 1).

    Single-camera, jersey-based: only players with a legible jersey number are tracked.
    """
    from backend.services.tendency_engine.players import analyze_players

    game = (await db.execute(
        select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id)
    )).scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    res = await db.execute(
        select(Event).where(Event.game_id == game_id, Event.organization_id == user.organization_id)
    )
    events = res.scalars().all()
    return analyze_players(events, game.sport or "football")


@router.get("/{game_id}/agent-log")
async def agent_log(
    game_id: str,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """UATP live action feed — what the agent did, why, and how confident it was.

    Powers the live status panel and the per-game audit trail. Returns chronological.
    """
    game = (await db.execute(
        select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id)
    )).scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    res = await db.execute(
        select(AgentLog)
        .where(AgentLog.game_id == game_id, AgentLog.organization_id == user.organization_id)
        .order_by(AgentLog.created_at.desc())
        .limit(min(limit, 500))
    )
    rows = list(res.scalars().all())
    rows.reverse()  # chronological for display

    return {
        "game_id": game_id,
        "entries": [
            {
                "id": str(r.id),
                "agent_name": r.agent_name,
                "agent_role": r.agent_role,
                "phase": r.phase,
                "action": r.action,
                "reason": r.reason,
                "confidence": r.confidence,
                "level": r.level,
                "detail": r.detail or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
