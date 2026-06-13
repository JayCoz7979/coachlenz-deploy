from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models.base import get_db
from backend.models.user import User
from backend.models.game import Game
from backend.models.job import Job
from backend.models.event import Event
from backend.services.auth import get_current_user

router = APIRouter(prefix="/games", tags=["ai-detect"])


@router.post("/{game_id}/auto-detect")
async def trigger_auto_detect(
    game_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue an AI play-detection job for a game that is already ingested (status=ready)."""
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
        payload={"game_id": game_id},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {"status": "queued", "job_id": str(job.id), "game_id": game_id}


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

    return {
        "game_id": game_id,
        "game_status": game.status,
        "job_status": job.status if job else None,
        "plays_detected": auto_count,
        "error": job.error_message if (job and job.status == "error") else None,
    }
