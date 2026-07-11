from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.services.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token, get_current_user
from backend.services.abuse_prevention import get_risk_score, fingerprint_request, flag_risk
from backend.services.trial import TRIAL_DAYS
from backend.services.email_service import send_welcome_email, send_password_reset_email, send_email_verification_code
from backend.services import twilio_verify
from backend.utils.timeutils import to_naive_utc
import uuid
import secrets
import hashlib
from slugify import slugify

router = APIRouter(prefix="/auth", tags=["auth"])

# Where the reset link points (the app the coach signs into).
APP_URL = "https://app.coachlenz.com"


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _validate_password(pw: str):
    if not pw or len(pw) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    org_name: str
    referral_code: str | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/register")
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    risk = get_risk_score(body.email)
    if risk >= 80:
        await flag_risk(None, None, "disposable_email", "high", {"email": body.email}, db)
        raise HTTPException(status_code=400, detail="Please use a valid email address")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    referred_by = None
    if body.referral_code:
        from backend.models.referral import ReferralCode
        rc = await db.execute(select(ReferralCode).where(ReferralCode.code == body.referral_code, ReferralCode.is_active == True))
        rc = rc.scalar_one_or_none()
        if rc:
            referred_by = rc.organization_id

    slug = slugify(body.org_name)
    org = Organization(
        name=body.org_name,
        slug=f"{slug}-{str(uuid.uuid4())[:8]}",
        subscription_tier="trial",
        is_trial=True,
        trial_ends_at=datetime.utcnow() + timedelta(days=TRIAL_DAYS),
        referred_by_org_id=referred_by,
    )
    db.add(org)
    await db.flush()

    user = User(
        organization_id=org.id,
        name=body.name,
        email=body.email,
        hashed_password=hash_password(body.password),
        role="owner",
    )
    db.add(user)
    await db.flush()

    if referred_by:
        from backend.models.referral import Referral
        referral = Referral(referrer_org_id=referred_by, referred_org_id=org.id)
        db.add(referral)

    await db.commit()
    try:
        await send_welcome_email(user.email, user.name)
    except Exception:
        pass

    access = create_access_token(str(user.id), str(org.id))
    refresh = create_refresh_token(str(user.id))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    await db.execute(update(User).where(User.id == user.id).values(last_login_at=datetime.utcnow()))
    await db.commit()
    access = create_access_token(str(user.id), str(user.organization_id))
    refresh = create_refresh_token(str(user.id))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@router.post("/refresh")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    result = await db.execute(select(User).where(User.id == payload["sub"], User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access = create_access_token(str(user.id), str(user.organization_id))
    return {"access_token": access, "token_type": "bearer"}


# ── Password reset (forgot password) ─────────────────────────────────────────
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Email a single-use, 1-hour reset link. Always returns 200 with the same
    message whether or not the email exists (no account enumeration)."""
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = _sha256(token)
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()
        try:
            await send_password_reset_email(user.email, user.name, f"{APP_URL}/reset-password?token={token}")
        except Exception:
            pass  # email is best-effort; never leak send failures to the caller
    return {"ok": True, "message": "If an account exists for that email, a reset link is on its way."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Consume a reset token: verify it matches an unexpired hash, set the new
    password, and clear the token (single use)."""
    _validate_password(body.new_password)
    token_hash = _sha256(body.token)
    # Expiry compared in SQL (func.now()) to avoid naive/aware datetime issues.
    result = await db.execute(
        select(User).where(User.reset_token_hash == token_hash, User.reset_token_expires > func.now())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")
    user.hashed_password = hash_password(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires = None
    await db.commit()
    return {"ok": True, "message": "Password reset. Sign in with your new password."}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the signed-in user's password after verifying the current one."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    _validate_password(body.new_password)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail="New password must be different from the current one.")
    await db.execute(update(User).where(User.id == user.id).values(hashed_password=hash_password(body.new_password)))
    await db.commit()
    return {"ok": True, "message": "Password updated."}


# ── Onboarding identity verification (email + phone, chargeback protection) ───
class VerifyEmailRequest(BaseModel):
    code: str


class SendPhoneRequest(BaseModel):
    phone: str


class VerifyPhoneRequest(BaseModel):
    code: str


@router.post("/send-email-code")
async def send_email_code(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    # Cooldown: each send sets the expiry to now+15min. If it's still >14min out, a
    # code went out under a minute ago — throttle so this can't be spammed (email
    # cost + sender-reputation damage). No extra column needed.
    exp = to_naive_utc(user.email_verify_expires)
    if exp is not None and exp > datetime.utcnow() + timedelta(minutes=14):
        raise HTTPException(status_code=429, detail="A code was just sent. Please wait a minute before requesting another.")
    code = f"{secrets.randbelow(1000000):06d}"
    await db.execute(update(User).where(User.id == user.id).values(
        email_verify_code_hash=_sha256(code),
        email_verify_expires=datetime.utcnow() + timedelta(minutes=15),
    ))
    await db.commit()
    try:
        await send_email_verification_code(user.email, user.name, code)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not send the verification email. Try again in a moment.")
    return {"ok": True, "message": f"We sent a 6-digit code to {user.email}."}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.email_verified:
        return {"ok": True, "email_verified": True}
    code = (body.code or "").strip()
    result = await db.execute(select(User).where(
        User.id == user.id,
        User.email_verify_code_hash == _sha256(code),
        User.email_verify_expires > func.now(),
    ))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=400, detail="That code is incorrect or has expired. Request a new one.")
    u.email_verified = True
    u.email_verify_code_hash = None
    u.email_verify_expires = None
    await db.commit()
    return {"ok": True, "email_verified": True}


@router.post("/send-phone-code")
async def send_phone_code(body: SendPhoneRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    phone = twilio_verify.normalize_phone(body.phone)
    if len(phone) < 11:
        raise HTTPException(status_code=422, detail="Enter a valid phone number.")
    await db.execute(update(User).where(User.id == user.id).values(phone=phone, phone_verified=False))
    await db.commit()
    twilio_verify.send_sms_code(phone)  # raises 503/400 on config/number issues
    return {"ok": True, "message": "We texted you a 6-digit code."}


@router.post("/verify-phone")
async def verify_phone(body: VerifyPhoneRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.phone:
        raise HTTPException(status_code=400, detail="Add your phone number first.")
    if not twilio_verify.check_sms_code(user.phone, (body.code or "").strip()):
        raise HTTPException(status_code=400, detail="That code is incorrect or has expired.")
    await db.execute(update(User).where(User.id == user.id).values(phone_verified=True))
    await db.commit()
    return {"ok": True, "phone_verified": True}
