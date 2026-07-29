"""
Staff management (Track 5.1): a head coach / owner invites coaching staff into
their organization, sets their role, and revokes access.

Staff are sub-accounts under the org (same organization_id), so they inherit the
org's subscription — no independent billing. Invites reuse the password-reset
mechanism: the invitee receives a token and sets their password via
/auth/reset-password. Revoke deactivates the user AND bumps token_version, so both
their access token (get_current_user filters is_active) and refresh tokens die
immediately.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import secrets
import hashlib

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.services.auth import get_current_user, get_current_org, require_permission, hash_password
from backend.services.permissions import CAN_INVITE_STAFF, STAFF_ASSIGNABLE_ROLES, role_permissions
from backend.services.email_service import send_staff_invite_email

router = APIRouter(prefix="/staff", tags=["staff"])

APP_URL = "https://app.coachlenz.com"
INVITE_EXPIRY_DAYS = 7

# Inviting, role changes, and revocation all require can_invite_staff (head coach /
# owner). Listing staff is open to any org member.
_require_invite = Depends(require_permission(CAN_INVITE_STAFF))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _staff_out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role,
            "is_active": u.is_active, "permissions": sorted(role_permissions(u.role))}


class InviteIn(BaseModel):
    email: EmailStr
    name: str
    role: str = "analyst"


class RoleIn(BaseModel):
    role: str


async def _target_in_org(user_id: str, inviter: User, db: AsyncSession) -> User:
    res = await db.execute(select(User).where(
        User.id == user_id, User.organization_id == inviter.organization_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your organization.")
    return target


@router.get("")
async def list_staff(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(
        User.organization_id == user.organization_id).order_by(User.created_at))
    return [_staff_out(u) for u in res.scalars().all()]


@router.post("/invite")
async def invite_staff(body: InviteIn, inviter: User = _require_invite,
                       org: Organization = Depends(get_current_org),
                       db: AsyncSession = Depends(get_db)):
    role = (body.role or "").strip().lower()
    if role not in STAFF_ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422,
                            detail=f"role must be one of: {', '.join(sorted(STAFF_ASSIGNABLE_ROLES))}")
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with that email already exists.")

    token = secrets.token_urlsafe(32)
    staff = User(
        organization_id=inviter.organization_id,
        name=body.name,
        email=body.email,
        # Unusable placeholder until the invitee sets their own password via the token.
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        role=role,
        is_active=True,
        reset_token_hash=_sha256(token),
        reset_token_expires=datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    invite_url = f"{APP_URL}/accept-invite?token={token}"
    try:
        await send_staff_invite_email(body.email, body.name, inviter.name, org.name, invite_url)
    except Exception:
        pass  # email is best-effort; the account + token still exist
    return {**_staff_out(staff), "invited": True}


@router.post("/{user_id}/role")
async def set_staff_role(user_id: str, body: RoleIn, inviter: User = _require_invite,
                         db: AsyncSession = Depends(get_db)):
    role = (body.role or "").strip().lower()
    if role not in STAFF_ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422,
                            detail=f"role must be one of: {', '.join(sorted(STAFF_ASSIGNABLE_ROLES))}")
    target = await _target_in_org(user_id, inviter, db)
    if target.role == "owner":
        raise HTTPException(status_code=403, detail="Cannot change the owner's role.")
    target.role = role
    await db.commit()
    return _staff_out(target)


@router.post("/{user_id}/revoke")
async def revoke_staff(user_id: str, inviter: User = _require_invite,
                       db: AsyncSession = Depends(get_db)):
    """Immediately remove a staff member's access: deactivate the account and bump
    token_version so their access and refresh tokens both stop working now."""
    target = await _target_in_org(user_id, inviter, db)
    if target.role == "owner":
        raise HTTPException(status_code=403, detail="Cannot revoke the owner.")
    if str(target.id) == str(inviter.id):
        raise HTTPException(status_code=400, detail="You can't revoke your own access.")
    target.is_active = False
    target.token_version = (target.token_version or 0) + 1
    await db.commit()
    return {"ok": True, "revoked": True, "user_id": str(target.id)}


@router.post("/{user_id}/reactivate")
async def reactivate_staff(user_id: str, inviter: User = _require_invite,
                           db: AsyncSession = Depends(get_db)):
    target = await _target_in_org(user_id, inviter, db)
    target.is_active = True
    await db.commit()
    return {"ok": True, "user_id": str(target.id), "is_active": True}
