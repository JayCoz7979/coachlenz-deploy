from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
import uuid
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.game import Game
from backend.services.auth import get_current_user, get_current_org
from backend.services.r2 import generate_presigned_upload_url, upload_fileobj

router = APIRouter(prefix="/upload", tags=["upload"])

MAX_FILE_SIZE = 20 * 1024 * 1024 * 1024  # 20GB


@router.get("/__ping")
async def _deploy_ping():
    return {"marker": "proxy-upload-v1"}

class UploadRequest(BaseModel):
    game_id: str
    file_name: str
    content_type: str = "video/mp4"
    file_size_bytes: Optional[int] = None

@router.post("/presign")
async def presign_upload(body: UploadRequest, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if body.file_size_bytes and body.file_size_bytes > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 20GB limit")
    result = await db.execute(select(Game).where(Game.id == body.game_id, Game.organization_id == org.id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    key = game.r2_key or f"games/{org.id}/{game.id}/{body.file_name}"
    presigned = generate_presigned_upload_url(key, body.content_type)
    await db.execute(update(Game).where(Game.id == body.game_id).values(r2_key=key, file_size_bytes=body.file_size_bytes))
    await db.commit()
    return {"upload_url": presigned["upload_url"], "key": key}

@router.post("/file")
async def upload_file_proxy(
    game_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Server-side proxy upload: the browser POSTs the file here (same-origin to the
    API, CORS already allowed), and the backend streams it to R2 with its own keys.
    No browser->R2 PUT, so R2 bucket CORS is irrelevant."""
    result = await db.execute(select(Game).where(Game.id == game_id, Game.organization_id == org.id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    key = game.r2_key or f"games/{org.id}/{game.id}/{file.filename}"
    try:
        # boto3 upload_fileobj is blocking — run it off the event loop.
        await run_in_threadpool(upload_fileobj, key, file.file, file.content_type or "video/mp4")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}")
    await db.execute(update(Game).where(Game.id == game_id).values(r2_key=key, status="processing"))
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
