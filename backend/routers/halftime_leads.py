"""Public endpoints for the free printable Halftime Sheet PDF (double opt-in).

  POST /leads/halftime-sheet          submit name + email (+ optional phone). Stores a
                                      pending lead and emails a confirmation link.
  POST /leads/halftime-sheet/confirm  {token} from that link. Confirms, then emails the PDF.
  POST /leads/halftime-sheet/resend   {email} or {token}: a fresh link for an expired,
                                      used, or lost one.

There is deliberately NO endpoint that returns the PDF: it only ever leaves the server
as an email attachment, after confirmation. Confirm is a POST (the frontend page sends
it when the coach clicks), so a mail scanner prefetching the GET link cannot burn the
single-use token. Unauthenticated, rate limited per IP, plus a per-address cooldown in
the service. A filled honeypot gets the normal success answer and stores nothing.
No SMS anywhere: phone is optional and never texted.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.services import halftime_leads as svc

router = APIRouter(prefix="/leads/halftime-sheet", tags=["leads"])


def get_lead_store(db: AsyncSession = Depends(get_db)) -> svc.LeadStore:
    return svc.SqlLeadStore(db)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _err(e: svc.LeadError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"detail": e.detail()})


class SubmitIn(BaseModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)
    phone: Optional[str] = Field(default=None, max_length=40)
    consent: bool = False
    # Honeypot: hidden from people, bots fill it in.
    company: Optional[str] = Field(default=None, max_length=200)


class ConfirmIn(BaseModel):
    token: str = Field(default="", max_length=400)


class ResendIn(BaseModel):
    email: Optional[str] = Field(default=None, max_length=320)
    token: Optional[str] = Field(default=None, max_length=400)


@router.get("/consent")
async def consent_text():
    """The exact consent line the form shows (and the row stores)."""
    return {"consent_text": svc.CONSENT_TEXT.split("] ", 1)[-1], "privacy_path": "/privacy"}


@router.post("")
@limiter.limit("5/minute;30/hour")
async def submit(body: SubmitIn, request: Request, store: svc.LeadStore = Depends(get_lead_store)):
    if (body.company or "").strip():
        return {"ok": True, "status": "pending", "message": svc.GENERIC_SUBMIT_MESSAGE}
    try:
        return await svc.submit_lead(store, name=body.name, email=body.email, phone=body.phone,
                                     consent=body.consent, ip=_ip(request))
    except svc.LeadError as e:
        return _err(e)


@router.post("/confirm")
@limiter.limit("20/minute")
async def confirm(body: ConfirmIn, request: Request, store: svc.LeadStore = Depends(get_lead_store)):
    try:
        return await svc.confirm_lead(store, token=body.token, ip=_ip(request))
    except svc.LeadError as e:
        return _err(e)


@router.post("/resend")
@limiter.limit("3/minute;20/hour")
async def resend(body: ResendIn, request: Request, store: svc.LeadStore = Depends(get_lead_store)):
    try:
        return await svc.resend_confirmation(store, email=body.email, token=body.token)
    except svc.LeadError as e:
        return _err(e)
