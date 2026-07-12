"""
Local file serve/upload endpoints — active only when R2 credentials are absent (beta/dev mode).
Files are stored in /tmp and reset on redeploy.
"""
import mimetypes
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from backend.services.r2 import _use_local, save_local_file, read_local_file

router = APIRouter(prefix="/files", tags=["files"])


@router.put("/upload/{key:path}")
async def local_upload(key: str, request: Request):
    if not _use_local():
        raise HTTPException(status_code=404)
    data = await request.body()
    try:
        save_local_file(key, data)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file key")
    return {"key": key, "size": len(data)}


@router.get("/{key:path}")
async def local_serve(key: str):
    if not _use_local():
        raise HTTPException(status_code=404)
    try:
        data = read_local_file(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file key")
    if data is None:
        raise HTTPException(status_code=404, detail="File not found")
    mime, _ = mimetypes.guess_type(key)
    return Response(content=data, media_type=mime or "application/octet-stream")
