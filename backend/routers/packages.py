from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
from slugify import slugify
from backend.models.base import get_db
from backend.models.user import User
from backend.models.comms import FilmPackage
from backend.services.auth import get_current_user
from backend.utils.timeutils import to_naive_utc

router = APIRouter(prefix="/packages", tags=["packages"])

class PackageCreate(BaseModel):
    title: str
    description: Optional[str] = None
    clip_ids: List[str]
    expires_in_days: Optional[int] = 7

@router.get("")
async def list_packages(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FilmPackage).where(FilmPackage.organization_id == user.organization_id).order_by(FilmPackage.created_at.desc()))
    packages = result.scalars().all()
    return [{"id": str(p.id), "title": p.title, "slug": p.slug, "share_token": p.share_token, "view_count": p.view_count, "expires_at": p.expires_at.isoformat() if p.expires_at else None} for p in packages]

@router.post("")
async def create_package(body: PackageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    slug = f"{slugify(body.title)}-{str(uuid.uuid4())[:6]}"
    expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    pkg = FilmPackage(
        organization_id=user.organization_id,
        title=body.title,
        description=body.description,
        slug=slug,
        clip_ids=body.clip_ids,
        expires_at=expires_at,
        created_by=user.id,
    )
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return {"id": str(pkg.id), "slug": pkg.slug, "share_token": pkg.share_token}

@router.get("/view/{token}")
async def view_package(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FilmPackage).where(FilmPackage.share_token == token))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    if pkg.expires_at and datetime.utcnow() > to_naive_utc(pkg.expires_at):
        raise HTTPException(status_code=410, detail="Package expired")
    await db.execute(update(FilmPackage).where(FilmPackage.id == pkg.id).values(view_count=FilmPackage.view_count + 1))
    await db.commit()
    return {"title": pkg.title, "description": pkg.description, "clip_ids": pkg.clip_ids}
