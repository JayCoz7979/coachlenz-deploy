from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.services.r2 import generate_presigned_upload_url, upload_fileobj, safe_object_name
from backend.services import film_upload
from backend.services.film_upload import (
    MSG_STORAGE,
    accept_relayed_part,
    abort_upload,
    finish_upload,
    read_capped,
    sign_parts,
    start_upload,
    upload_status,
)
from backend.routers.games import GameCreate
from backend.ratelimit import limiter

router = APIRouter(prefix="/upload", tags=["upload"])


class UploadRequest(BaseModel):
    game_id: str
    file_name: str
    content_type: str = "video/mp4"
    file_size_bytes: Optional[int] = None


class TokenBody(BaseModel):
    upload_token: str


class SignBody(BaseModel):
    upload_token: str
    part_numbers: list[int]


class MultipartComplete(GameCreate):
    upload_token: str


def _public_base(request: Request) -> str:
    return str(request.base_url)


@router.post("/presign")
async def presign_upload(body: UploadRequest, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if body.file_size_bytes is not None:
        film_upload.assert_file_size(body.file_size_bytes)
    result = await db.execute(select(Game).where(Game.id == body.game_id, Game.organization_id == org.id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    key = game.r2_key or f"games/{org.id}/{game.id}/{safe_object_name(body.file_name)}"
    presigned = generate_presigned_upload_url(key, body.content_type)
    await db.execute(update(Game).where(Game.id == body.game_id).values(r2_key=key, file_size_bytes=body.file_size_bytes))
    await db.commit()
    return {"upload_url": presigned["upload_url"], "key": key}


@router.post("/multipart/init")
@limiter.limit("30/minute")
async def init_multipart(
    body: GameCreate,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Start a direct-to-storage multipart upload.

    Does not create a game and does not consume a trial slot. The browser PUTs
    each chunk to the URL from /upload/multipart/sign (R2, or this API in local
    mode). Call /upload/multipart/complete after every chunk is stored.
    """
    return await start_upload(db, user, org, body)


@router.post("/multipart/sign")
@limiter.limit("120/minute")
async def sign_multipart(
    body: SignBody,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    return sign_parts(org, body.upload_token, body.part_numbers, _public_base(request))


@router.post("/multipart/status")
@limiter.limit("120/minute")
async def multipart_status(
    body: TokenBody,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    """Chunks already in storage, so an interrupted upload can resume."""
    return upload_status(org, body.upload_token)


@router.put("/multipart/part/{part_number}")
@limiter.limit("120/minute")
async def relay_part(
    part_number: int,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    upload_token: str = Header(alias="X-Upload-Token"),
):
    """Same-origin fallback for one chunk.

    The browser tries the presigned storage URL first. If that PUT cannot leave
    the browser (typically because the R2 bucket has no CORS rule yet), it posts
    the chunk here instead. The body is capped at one part, which is small
    enough to finish inside Railway's 300s request cutoff.
    """
    film_upload.enforce_proxy_limit(request.headers.get("content-length"))
    data = await read_capped(request, film_upload.SINGLE_REQUEST_LIMIT)
    return accept_relayed_part(org, upload_token, part_number, data)


@router.post("/multipart/complete")
@limiter.limit("30/minute")
async def complete_multipart(
    body: MultipartComplete,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Assemble the film, then create the game and reserve the trial slot."""
    return await finish_upload(db, user, org, body.upload_token, body)


@router.post("/multipart/abort")
@limiter.limit("30/minute")
async def abort_multipart(
    body: TokenBody,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    return abort_upload(org, body.upload_token)


@router.post("/file")
@limiter.limit("20/minute")
async def upload_file_proxy(
    game_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Legacy single-request upload. Refuses bodies that cannot finish well under
    Railway's 300s edge timeout. New clients use /upload/multipart/* instead."""
    film_upload.enforce_proxy_limit(request.headers.get("content-length"))
    result = await db.execute(select(Game).where(Game.id == game_id, Game.organization_id == org.id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    key = game.r2_key or f"games/{org.id}/{game.id}/{safe_object_name(file.filename)}"
    try:
        # boto3 upload_fileobj is blocking. Run it off the event loop.
        await run_in_threadpool(upload_fileobj, key, file.file, file.content_type or "video/mp4")
    except Exception as e:
        raise HTTPException(status_code=502, detail=MSG_STORAGE)
    # File is now in storage. Point the game at it and enqueue ingest only now,
    # so the worker probes a file that exists.
    await db.execute(update(Game).where(Game.id == game_id).values(r2_key=key, status="processing"))
    db.add(Job(organization_id=org.id, job_type="ingest", payload={"game_id": str(game_id)}))
    await db.commit()
    return {"ok": True, "key": key, "status": "processing"}


@router.post("/complete")
async def complete_upload(game_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).where(Game.id == game_id, Game.organization_id == user.organization_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    await db.execute(update(Game).where(Game.id == game_id).values(status="processing"))
    await db.commit()
    return {"ok": True, "status": "processing"}
