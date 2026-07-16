from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.source_connection import SourceConnection
from backend.services.auth import get_current_user, get_current_org
from backend.services.encryption import encrypt_json

router = APIRouter(prefix="/connections", tags=["connections"])

SUPPORTED_PROVIDERS = {"hudl", "nfhs"}


class ConnectRequest(BaseModel):
    provider: str
    email: Optional[str] = None
    password: Optional[str] = None
    # Netscape-format cookie text exported from a logged-in browser. More reliable
    # than headless login (Hudl's bot-detection often blocks automated sign-in) and
    # the recommended way to pull HD private film. Stored encrypted, per-org.
    cookies: Optional[str] = None


def _public(c: SourceConnection) -> dict:
    return {
        "provider": c.provider,
        "account_email": c.account_email,
        "status": c.status,
        "last_error": c.last_error,
        "last_verified_at": c.last_verified_at.isoformat() if c.last_verified_at else None,
        "connected_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("")
async def list_connections(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceConnection).where(SourceConnection.organization_id == org.id)
    )
    return [_public(c) for c in result.scalars().all()]


@router.post("")
async def connect_source(
    body: ConnectRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    provider = body.provider.lower().strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    email = (body.email or "").strip()
    has_login = bool(email and body.password)
    cookies = (body.cookies or "").strip()
    has_cookies = bool(cookies)
    if not (has_login or has_cookies):
        raise HTTPException(
            status_code=400,
            detail="Provide your login (email + password) or exported cookies. "
                   "Cookies are recommended for private HD film.",
        )

    creds = {}
    if has_login:
        creds["email"] = email
        creds["password"] = body.password
    if has_cookies:
        creds["cookies"] = cookies
    encrypted = encrypt_json(creds)
    account_email = email or "cookies"

    existing = await db.execute(
        select(SourceConnection).where(
            SourceConnection.organization_id == org.id,
            SourceConnection.provider == provider,
        )
    )
    conn = existing.scalar_one_or_none()
    if conn:
        conn.account_email = account_email
        conn.encrypted_credentials = encrypted
        conn.status = "connected"
        conn.last_error = None
        conn.updated_at = datetime.utcnow()
    else:
        conn = SourceConnection(
            organization_id=org.id,
            provider=provider,
            account_email=account_email,
            encrypted_credentials=encrypted,
            status="connected",
        )
        db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _public(conn)


@router.delete("/{provider}")
async def disconnect_source(
    provider: str,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(SourceConnection).where(
            SourceConnection.organization_id == org.id,
            SourceConnection.provider == provider.lower().strip(),
        )
    )
    await db.commit()
    return {"ok": True}
