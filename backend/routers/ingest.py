from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, HttpUrl
from typing import Optional
import uuid
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.services.trial import can_upload_game, is_trial_active
from backend.services.sports import assert_sport_allowed

router = APIRouter(prefix="/ingest", tags=["ingest"])

SUPPORTED_SOURCES = [
    "youtube.com", "youtu.be",
    "hudl.com",
    "vimeo.com",
    "drive.google.com",
    "dropbox.com",
    "facebook.com", "fb.watch",
    "twitter.com", "x.com",
    "instagram.com",
    "tiktok.com",
    "streamable.com",
    "dailymotion.com",
    "wistia.com",
    "loom.com",
]

def detect_source_type(url: str) -> str:
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "hudl.com" in url_lower:
        return "hudl"
    if "vimeo.com" in url_lower:
        return "vimeo"
    if "drive.google.com" in url_lower:
        return "google_drive"
    if "dropbox.com" in url_lower:
        return "dropbox"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    if "nfhsnetwork.com" in url_lower:
        return "nfhs"
    return "generic"


class IngestURLRequest(BaseModel):
    url: str
    title: str
    sport: str = "football"
    team_id: Optional[str] = None
    opponent: Optional[str] = None
    game_date: Optional[str] = None
    is_home: Optional[bool] = None


@router.post("/url")
async def ingest_from_url(
    body: IngestURLRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    if not can_upload_game(org):
        raise HTTPException(status_code=403, detail="Trial game limit reached. Upgrade to upload more games.")

    # Sport lock: a client can only analyze film for the sport(s) their plan
    # includes (chosen at onboarding). Warns instead of silently mis-analyzing.
    assert_sport_allowed(org, body.sport)

    source_type = detect_source_type(body.url)

    game = Game(
        organization_id=org.id,
        team_id=body.team_id,
        title=body.title,
        sport=body.sport,
        opponent=body.opponent,
        is_home=body.is_home,
        status="queued",
        is_trial_game=is_trial_active(org),
    )
    if body.game_date:
        from datetime import date
        try:
            game.game_date = date.fromisoformat(body.game_date)
        except ValueError:
            pass

    db.add(game)
    await db.flush()

    job = Job(
        organization_id=org.id,
        job_type="ingest",
        payload={
            "game_id": str(game.id),
            "source_url": body.url,
            "source_type": source_type,
        },
    )
    db.add(job)

    if is_trial_active(org):
        await db.execute(
            update(Organization)
            .where(Organization.id == org.id)
            .values(trial_games_used=Organization.trial_games_used + 1)
        )

    await db.commit()

    return {
        "game_id": str(game.id),
        "job_id": str(job.id),
        "status": "queued",
        "source_type": source_type,
        "message": f"Import queued from {source_type}. Processing usually takes 1–5 minutes.",
    }


@router.get("/job/{job_id}")
async def get_ingest_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.organization_id == user.organization_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": str(job.id),
        "status": job.status,
        "error_message": job.error_message,
        "result": job.result,
        "created_at": job.created_at.isoformat(),
    }
