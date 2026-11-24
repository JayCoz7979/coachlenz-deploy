"""
Public conversion-funnel endpoints: the anonymous event beacon and non-converter
lead capture. Both are unauthenticated (a visitor has no account yet) and rate
limited. The beacon only accepts the anonymous client events; the two signup steps
are emitted server-side (auth.register, onboarding.choose_sports) so they cannot be
spoofed from the browser.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.services import funnel as funnel_svc

from backend.config import settings
from backend.services.waitlist_capture import (
    FULL_WAITLIST_SOURCES,
    WAITLIST_ROLES,
    apply_repeat,
    canonicalize_source,
    new_lead_kwargs,
)

# Sports a waitlist visitor can name. Basketball and football are the launch
# sports; the others are there so a coach in a different sport can still sign up.
WAITLIST_SPORTS = ("basketball", "football", "soccer", "volleyball", "other")

router = APIRouter(tags=["funnel"])


class EventIn(BaseModel):
    event: str
    anon_id: Optional[str] = None
    path: Optional[str] = None
    source: Optional[str] = None
    meta: Optional[dict] = None


@router.post("/funnel/event")
@limiter.limit("60/minute")
async def track_event(body: EventIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Record one anonymous top-of-funnel event. Unknown or server-only events are
    silently ignored (still 200) so a spoofed or stale beacon never surfaces an error
    in the visitor's browser or lets the client forge a signup step."""
    if body.event in funnel_svc.ALLOWED_CLIENT_EVENTS:
        await funnel_svc.record_event(
            db, body.event, anon_id=(body.anon_id or None),
            path=body.path, source=body.source, meta=body.meta or {},
        )
    return {"ok": True}


def _clean(v: Optional[str], limit: int) -> Optional[str]:
    if v is None:
        return None
    v = " ".join(v.split())
    if not v:
        return None
    if len(v) > limit:
        raise ValueError(f"That value is too long (max {limit} characters).")
    return v


class LeadIn(BaseModel):
    email: EmailStr
    source: Optional[str] = None
    # first_name and role are required on the full waitlist sources. The older
    # email-only callers omit them, and that still works.
    first_name: Optional[str] = None
    school: Optional[str] = None
    sport: Optional[str] = None
    role: Optional[str] = None
    lead_magnet: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    referrer: Optional[str] = None
    landing_path: Optional[str] = None
    ref_code: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("First name is required.")
        return _clean(v, 80)

    @field_validator("school")
    @classmethod
    def _school(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, 200)

    @field_validator("source", "lead_magnet", "referrer", "landing_path", "ref_code")
    @classmethod
    def _short_tag(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, 120)

    @field_validator("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
    @classmethod
    def _utm(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, 120)

    @field_validator("sport")
    @classmethod
    def _sport(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            return None
        if v not in WAITLIST_SPORTS:
            raise ValueError("Sport must be basketball, football, soccer, volleyball, or other.")
        return v

    @field_validator("role")
    @classmethod
    def _role(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            return None
        if v == "player":
            return v
        if v not in WAITLIST_ROLES:
            raise ValueError("Role is not one of the allowed values.")
        return v

    @model_validator(mode="after")
    def _waitlist_requires_identity(self):
        source = canonicalize_source(self.source)
        if source not in FULL_WAITLIST_SOURCES:
            return self
        if not self.first_name:
            raise ValueError("First name is required.")
        if not self.role:
            raise ValueError("Please tell us your role.")
        return self


def _new_lead(email: str, source: str, body: LeadIn):
    from backend.models.funnel import MarketingLead
    return MarketingLead(**new_lead_kwargs(email, source, body))


@router.post("/leads")
@limiter.limit("10/minute")
async def capture_lead(body: LeadIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Capture a visitor email for the waitlist or the nurture list.

    Idempotent: a repeat email updates name, role, school, sport, lead magnet,
    and UTM values on that one row when those were sent. It does not send email.
    A bad email, an empty name, or an unknown role never reaches the insert.
    """
    from backend.models.funnel import MarketingLead
    email = str(body.email).lower().strip()
    source = canonicalize_source(body.source)
    if (body.role or "") == "player":
        raise HTTPException(status_code=422, detail="Player isn't available on the waitlist.")
    try:
        existing = (await db.execute(
            select(MarketingLead).where(func.lower(MarketingLead.email) == email)
        )).scalar_one_or_none()
        if existing is None:
            db.add(_new_lead(email, source, body))
        else:
            apply_repeat(existing, body, source)
        await db.commit()
    except IntegrityError:
        # Two requests inserted the same email at once. The unique index already
        # kept a single row, so the visitor is on the list.
        try:
            await db.rollback()
        except Exception:
            pass
        try:
            existing = (await db.execute(
                select(MarketingLead).where(func.lower(MarketingLead.email) == email)
            )).scalar_one_or_none()
            if existing is not None:
                apply_repeat(existing, body, source)
                await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Could not save that just now. Please try again.")
    # ref_code is stored on the row and does not create a referral or a reward.
    return {"ok": True}
