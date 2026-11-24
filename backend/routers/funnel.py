"""
Public conversion-funnel endpoints: the anonymous event beacon and non-converter
lead capture. Both are unauthenticated (a visitor has no account yet) and rate
limited. The beacon only accepts the anonymous client events; the two signup steps
are emitted server-side (auth.register, onboarding.choose_sports) so they cannot be
spoofed from the browser.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.services import funnel as funnel_svc

# Sports a waitlist visitor can name. Basketball and football are the launch
# sports; the others are there so a coach in a different sport can still sign up.
WAITLIST_SPORTS = ("basketball", "football", "soccer", "volleyball", "other")

# Stored slugs for the "I am a..." select. Labels live in the form.
WAITLIST_ROLES = (
    "head_coach",
    "assistant_coach",
    "athletic_director",
    "school_admin",
    "film_coordinator",
    "parent",
    "player",
    "other",
)

# Sources that are the launch waitlist, not the older email-only "keep me posted"
# box. Those rows must carry a name, a role, and an explicit email consent.
WAITLIST_SOURCES = frozenset({
    "waitlist",
    "app-home",
    "app-onboarding",
    "app-waitlist",
    "marketing-site",
})

# Text the checkbox shows. Bump the version if that sentence changes.
EMAIL_CONSENT_TEXT = "Email me launch updates and coaching resources."
EMAIL_CONSENT_VERSION = "2026-11-24"

# Fields a repeat submit may change on the row for THAT email. Never email,
# source, or created_at, and never a different row.
_REPEAT_FIELDS = (
    "name", "school", "sport", "role", "lead_magnet",
    "utm_source", "utm_medium", "utm_campaign",
)

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
    # Name and role are required on the waitlist sources. The older email-only
    # callers (the open homepage "Keep me posted" box and the film-time calculator)
    # omit them, and that still works.
    name: Optional[str] = None
    school: Optional[str] = None
    sport: Optional[str] = None
    role: Optional[str] = None
    role_other: Optional[str] = None
    lead_magnet: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    email_consent: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("Name is required.")
        return _clean(v, 100)

    @field_validator("school", "source")
    @classmethod
    def _school_or_source(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, 200)

    @field_validator("role_other")
    @classmethod
    def _role_other(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, 100)

    @field_validator("lead_magnet")
    @classmethod
    def _magnet(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, 80)

    @field_validator("utm_source", "utm_medium", "utm_campaign")
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
        v = v.strip().lower().replace(" ", "_")
        if not v:
            return None
        if v not in WAITLIST_ROLES:
            raise ValueError(
                "Role must be head coach, assistant coach, athletic director, "
                "principal / school admin, video / film coordinator, parent, player, or other."
            )
        return v

    @model_validator(mode="after")
    def _waitlist_requires_identity(self):
        source = (self.source or "").strip().lower()
        if source not in WAITLIST_SOURCES:
            return self
        if not self.name:
            raise ValueError("Name is required.")
        if not self.role:
            raise ValueError("Please tell us your role.")
        if not self.email_consent:
            raise ValueError("Please agree to receive launch updates.")
        return self


def _apply_lead_details(row, body: LeadIn) -> None:
    """Update the volunteered fields on the row for this email only.

    A blank field does not erase a value they already gave us. role_other is
    kept only when the role is other. Consent is recorded when they check the
    box, and a later submit that omits the box does not take consent away.
    Email, source, and created_at are not touched.
    """
    for field in _REPEAT_FIELDS:
        value = getattr(body, field)
        if value:
            setattr(row, field, value)
    if body.role == "other":
        if body.role_other:
            row.role_other = body.role_other
    elif body.role:
        row.role_other = None
    if body.email_consent:
        row.email_consent_at = datetime.utcnow()
        row.email_consent_version = EMAIL_CONSENT_VERSION


def _new_lead(email: str, source: str, body: LeadIn):
    from backend.models.funnel import MarketingLead
    row = MarketingLead(
        email=email,
        source=source,
        name=body.name,
        school=body.school,
        sport=body.sport,
        role=body.role,
        role_other=body.role_other if body.role == "other" else None,
        lead_magnet=body.lead_magnet,
        utm_source=body.utm_source,
        utm_medium=body.utm_medium,
        utm_campaign=body.utm_campaign,
    )
    if body.email_consent:
        row.email_consent_at = datetime.utcnow()
        row.email_consent_version = EMAIL_CONSENT_VERSION
    return row


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
    source = (body.source or "landing")[:120]
    try:
        existing = (await db.execute(
            select(MarketingLead).where(func.lower(MarketingLead.email) == email)
        )).scalar_one_or_none()
        if existing is None:
            db.add(_new_lead(email, source, body))
        else:
            _apply_lead_details(existing, body)
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
                _apply_lead_details(existing, body)
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
    return {"ok": True}
