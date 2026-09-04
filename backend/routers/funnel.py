"""
Public conversion-funnel endpoints: the anonymous event beacon and non-converter
lead capture. Both are unauthenticated (a visitor has no account yet) and rate
limited. The beacon only accepts the anonymous client events; the two signup steps
are emitted server-side (auth.register, onboarding.choose_sports) so they cannot be
spoofed from the browser.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.services import funnel as funnel_svc

router = APIRouter(tags=["funnel"])


class EventIn(BaseModel):
    event: str
    anon_id: Optional[str] = None
    path: Optional[str] = None
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
            path=body.path, meta=body.meta or {},
        )
    return {"ok": True}


class LeadIn(BaseModel):
    email: EmailStr
    source: Optional[str] = None


@router.post("/leads")
@limiter.limit("10/minute")
async def capture_lead(body: LeadIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Capture a non-converter's email so they can be nurtured. Idempotent: a repeat
    email hits the lower(email) unique index and is treated as success."""
    from backend.models.funnel import MarketingLead
    try:
        db.add(MarketingLead(email=str(body.email).lower().strip(), source=(body.source or "landing")))
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
    return {"ok": True}
