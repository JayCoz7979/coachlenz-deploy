import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.config import settings
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization

bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_access_token(user_id: str, org_id: str) -> str:
    payload = {
        "sub": user_id,
        "org": org_id,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=30),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=30),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    result = await db.execute(select(User).where(User.id == payload["sub"], User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_org(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == user.organization_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

def require_role(*roles):
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


# ── Platform super-admin ─────────────────────────────────────────────────────
# CRITICAL: `role="owner"` is a PER-ORG role — every customer is the owner of
# their own org. It must NEVER gate the /admin/* surface (which can edit any org's
# plan and entitlements). Platform admin = an allowlisted email OR an org whose
# admin_level is explicitly a platform tier. Default-deny.
_PLATFORM_ADMIN_LEVELS = {"platform", "super"}


def _admin_email_allowlist() -> set:
    return {e.strip().lower() for e in (settings.ADMIN_EMAILS or "").split(",") if e.strip()}


def is_platform_admin(user: User, org: Organization) -> bool:
    if user.email and user.email.strip().lower() in _admin_email_allowlist():
        return True
    return (org.admin_level or "").strip().lower() in _PLATFORM_ADMIN_LEVELS


async def require_admin(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> User:
    """Gate for /admin/* endpoints. Returns 404 (not 403) so the admin surface
    isn't advertised to a probing non-admin."""
    if not is_platform_admin(user, org):
        raise HTTPException(status_code=404, detail="Not found")
    return user


# ── Scouting RBAC ────────────────────────────────────────────────────────────
# Role definitions live in scout_roles (no framework import) so they are testable
# without the web stack; re-exported here for callers that import from auth.
from backend.services.scout_roles import (  # noqa: E402
    SCOUT_REVIEWER_ROLES, SCOUT_ASSIGNABLE_ROLES, can_review_scout,
)


def require_scout_reviewer(user: User = Depends(get_current_user)) -> User:
    if not can_review_scout(user):
        raise HTTPException(
            status_code=403,
            detail="Review authority required. Only a head coach, coordinator, reviewer, or owner can sign off a scouting report.",
        )
    return user

def require_coach_tenure(org: Organization = Depends(get_current_org)):
    if not org.has_coach_tenure_access:
        raise HTTPException(status_code=403, detail="Not found")
    return org
