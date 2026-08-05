"""
Local file serve/upload endpoints — active only when R2 credentials are absent (beta/dev mode).
Files are stored in /tmp and reset on redeploy.
"""
import mimetypes
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from backend.config import settings
from backend.services.r2 import _use_local, save_local_file, read_local_file

router = APIRouter(prefix="/files", tags=["files"])


def _files_disabled() -> bool:
    """Local file serving is a NON-PROD fallback for when R2 is unconfigured. It
    must never serve in production: these endpoints are unauthenticated and
    cross-org, so if R2 creds ever regressed in prod they would silently become an
    open object store (any key readable/writable by anyone). Fail closed in prod
    regardless of R2 state; media playback there always comes from R2."""
    return not _use_local() or settings.ENVIRONMENT == "production"


@router.put("/upload/{key:path}")
async def local_upload(key: str, request: Request):
    if _files_disabled():
        raise HTTPException(status_code=404)
    data = await request.body()
    try:
        save_local_file(key, data)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file key")
    return {"key": key, "size": len(data)}


@router.get("/{key:path}")
async def local_serve(key: str):
    if _files_disabled():
        raise HTTPException(status_code=404)
    try:
        data = read_local_file(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file key")
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    mime, _ = mimetypes.guess_type(key)
    return Response(content=data, media_type=mime or "application/octet-stream")
