"""
Local file serve/upload endpoints. Active only when R2 credentials are absent
(dev and tests). Files are stored under LOCAL_STORAGE_DIR and reset on redeploy.

Production never serves these routes. Film chunks go to R2 with presigned
UploadPart URLs, and playback URLs are presigned against R2 as well.
"""
import mimetypes
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import Response
from backend.config import settings
from backend.services import r2
from backend.services.film_upload import read_capped
from backend.services.multipart_store import MultipartError, verify_part_signature, write_part

router = APIRouter(prefix="/files", tags=["files"])


def _use_local() -> bool:
    # Module-level so tests can force local mode on or off without touching R2.
    return r2._use_local()


def read_local_file(key: str):
    return r2.read_local_file(key)


def save_local_file(key: str, data: bytes):
    return r2.save_local_file(key, data)


def _files_disabled() -> bool:
    """Local file serving is a NON-PROD fallback for when R2 is unconfigured. It
    must never serve in production: these endpoints are unauthenticated and
    cross-org, so if R2 creds ever regressed in prod they would silently become an
    open object store (any key readable/writable by anyone). Fail closed in prod
    regardless of R2 state; media playback there always comes from R2."""
    return not _use_local() or settings.ENVIRONMENT == "production"


@router.put("/multipart/{upload_id}/{part_number}")
async def local_part(upload_id: str, part_number: int, request: Request, sig: str = Query("")):
    """One chunk of a film, in local-storage mode. The query signature is the
    presigned credential, bound to this upload id, part number, and a max size."""
    if _files_disabled():
        raise HTTPException(status_code=404)
    try:
        claims = verify_part_signature(sig, upload_id, part_number)
    except MultipartError:
        raise HTTPException(status_code=403, detail="Invalid upload signature")
    try:
        cap = int(claims.get("max") or 0)
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        raise HTTPException(status_code=403, detail="Invalid upload signature")
    data = await read_capped(request, cap)
    if not data:
        raise HTTPException(status_code=400, detail="That chunk was empty.")
    try:
        etag = write_part(claims["key"], upload_id, part_number, data)
    except MultipartError:
        raise HTTPException(status_code=400, detail="Upload session not found")
    return Response(status_code=200, headers={"ETag": etag})


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
    # In-progress chunks are not a public object. Only the assembled film is.
    if key == ".multipart" or key.startswith(".multipart/"):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data = read_local_file(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file key")
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    mime, _ = mimetypes.guess_type(key)
    return Response(content=data, media_type=mime or "application/octet-stream")
