from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models.base import get_db
from backend.models.user import User
from backend.models.game import Game
from backend.models.job import Job
from backend.models.event import Event
from backend.models.agent_log import AgentLog
from backend.services.auth import get_current_user

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

    # Greedy nearest-in-time matching, one prediction per truth play.
    used = set()
    matches = []
    for t in truth:
        best_i, best_d = None, ACCURACY_MATCH_WINDOW_S + 1
        for i, p in enumerate(pred):
            if i in used:
                continue
            d = abs((p.time_seconds or 0) - (t.time_seconds or 0))
            if d <= ACCURACY_MATCH_WINDOW_S and d < best_d:
                best_i, best_d = i, d
        if best_i is not None:
            used.add(best_i)
            matches.append((t, pred[best_i]))

    recall = len(matches) / len(truth) if truth else 0
    precision = len(matches) / len(pred) if pred else 0

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
        "ai_plays": len(pred),
        "matched": len(matches),
        "recall_pct": round(recall * 100, 1),       # of real plays, how many AI caught
        "precision_pct": round(precision * 100, 1),  # of AI plays, how many were real
        "match_window_s": ACCURACY_MATCH_WINDOW_S,
        "attribute_accuracy": attr,
    }


@router.post("/{game_id}/auto-detect")
async def trigger_auto_detect(
    game_id: str,
    dry_run: bool = False,
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

    # Check for an already-running detect job
    existing = await db.execute(
        select(Job).where(
            Job.job_type == "ai_detect",
            Job.status.in_(["queued", "running"]),
            Job.payload["game_id"].as_string() == game_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_queued", "game_id": game_id}

    job = Job(
        organization_id=user.organization_id,
        job_type="ai_detect",
        payload={"game_id": game_id, "dry_run": dry_run},
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
        "game_status": game.status,
        "job_status": job.status if job else None,
        "plays_detected": auto_count,
        "needs_review": needs_review,
        "dry_run": bool((job.payload or {}).get("dry_run")) if job else False,
        "error": job.error_message if (job and job.status == "error") else None,
    }


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
