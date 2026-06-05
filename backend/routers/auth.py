from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.services.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token, get_current_user
from backend.services.abuse_prevention import get_risk_score, fingerprint_request, flag_risk
from backend.services.trial import TRIAL_DAYS
from backend.services.email_service import send_welcome_email
import uuid
from python_slugify import slugify

router = APIRouter(prefix="/auth", tags=["auth"])

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
