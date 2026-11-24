"""
Public conversion-funnel endpoints: the anonymous event beacon and non-converter
lead capture. Both are unauthenticated (a visitor has no account yet) and rate
limited. The beacon only accepts the anonymous client events; the two signup steps
are emitted server-side (auth.register, onboarding.choose_sports) so they cannot be
spoofed from the browser.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.services import funnel as funnel_svc

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


class LeadIn(BaseModel):
    email: EmailStr
    source: Optional[str] = None
    # Optional waitlist context. Older callers (the landing page and the film-time
    # calculator) send email and source only, and that still works.
    school: Optional[str] = None
    sport: Optional[str] = None

    @field_validator("school", "source")
    @classmethod
    def _clean_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 200:
            raise ValueError("That value is too long.")
        return v

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


def _apply_lead_details(row, body: LeadIn) -> None:
    """Fill school and sport when a repeat visitor sends them. Never blank out a
    value they already gave us."""
    if body.school:
        row.school = body.school
    if body.sport:
        row.sport = body.sport


@router.post("/leads")
@limiter.limit("10/minute")
async def capture_lead(body: LeadIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Capture a visitor email for the waitlist or the nurture list. Idempotent: a
    repeat email updates school or sport when those were sent, and still returns
    success. A bad email never reaches this function (the body model rejects it)."""
    from backend.models.funnel import MarketingLead
    email = str(body.email).lower().strip()
    source = (body.source or "landing")[:120]
    try:
        existing = (await db.execute(
            select(MarketingLead).where(func.lower(MarketingLead.email) == email)
        )).scalar_one_or_none()
        if existing is None:
            db.add(MarketingLead(email=email, source=source, school=body.school, sport=body.sport))
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
        if body.school or body.sport:
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
