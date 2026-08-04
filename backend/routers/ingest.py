from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, HttpUrl
from typing import Optional
import uuid
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.services.trial import can_upload_game, is_trial_active, reserve_trial_game_slot
from backend.services.sports import assert_sport_allowed
from backend.services.entitlements import assert_ready_to_analyze
from backend.services.legal import assert_student_consent
from backend.ratelimit import limiter
from backend.utils.url_guard import validate_public_http_url
from backend.services.ingest_classify import (
    SUPPORTED_SOURCES,
    detect_source_type,
    classify_ingest_url,
)

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestURLRequest(BaseModel):
    url: str
    title: str
    sport: str = "football"
    team_id: Optional[str] = None
    opponent: Optional[str] = None
    game_date: Optional[str] = None
    is_home: Optional[bool] = None


@router.post("/url")
@limiter.limit("20/minute")
async def ingest_from_url(
    body: IngestURLRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    if not can_upload_game(org):
        raise HTTPException(status_code=403, detail="Trial game limit reached. Upgrade to upload more games.")

    # Entitlements: an active trial must verify email + lock a sport before it can
    # import film (URL ingest auto-chains into detection).
    assert_ready_to_analyze(org, user)

    # COPPA/FERPA: imported film carries minors' images and the AI extracts jersey
    # numbers (individual identifiers), so the org must have made the student-data
    # authority attestation BEFORE any minors' film is fetched, stored, or analyzed.
    await assert_student_consent(db, org.id)

    # Sport lock: a client can only analyze film for the sport(s) their plan
    # includes (chosen at onboarding). Warns instead of silently mis-analyzing.
    assert_sport_allowed(org, body.sport)

    # SSRF guard: the server will fetch this URL with yt-dlp/ffprobe. Reject
    # non-http(s) schemes and any private/internal/metadata destination.
    try:
        validate_public_http_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Authoritative, race-free trial-cap gate (the check above is a friendly
    # pre-check only). Reserves the slot atomically in this transaction.
    if not await reserve_trial_game_slot(db, org):
        raise HTTPException(status_code=403, detail="Trial game limit reached. Upgrade to upload more games.")

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

    await db.commit()

    return {
        "game_id": str(game.id),
        "job_id": str(job.id),
        "status": "queued",
        "source_type": source_type,
        "message": f"Import queued from {source_type}. Processing usually takes 1–5 minutes.",
    }


class CheckURLRequest(BaseModel):
    url: str


@router.post("/check-url")
@limiter.limit("60/minute")
async def check_url(
    body: CheckURLRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Classify a pasted link the same way the ingest worker will treat it, so the
    import UI can show a TRUTHFUL 'no account needed' badge (or the right warning)
    before the coach commits. Pure classification — no fetch, no side effects."""
    return classify_ingest_url(body.url)


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
