"""
Free printable Halftime Sheet PDF, offered on /live-tracker for a name + valid email.

Public, no login. Phone is OPTIONAL and never required; it is stored only because the
visitor volunteered it, and nothing here (or anywhere in CoachLenz) texts it.

  POST /leads/halftime-pdf                       validate + store the lead, return a
                                                 download link (shown after submit)
  GET  /leads/halftime-pdf/download/{token}      the PDF, for a token issued above

Abuse controls: per-IP rate limits (shared slowapi limiter), a honeypot field
(`website`) that real visitors never see, and server-side email validation (format,
disposable-domain blocklist, MX/domain lookup) in backend/services/email_check.py.
"""
import re
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.lead_magnet import LeadMagnetLead
from backend.ratelimit import limiter
from backend.services.email_check import EmailRejected, validate_lead_email
from backend.services.halftime_pdf import PDF_FILENAME, halftime_sheet_pdf

router = APIRouter(prefix="/leads", tags=["leads"])

SOURCE = "halftime_pdf"
DOWNLOAD_PATH = "/leads/halftime-pdf/download/{token}"
# Shown next to the checkbox on /live-tracker and stored with each lead as the record
# of what the visitor agreed to. Keep frontend/app/live-tracker/page.tsx in sync.
CONSENT_TEXT = ("I agree that CoachLenz may email me the Halftime Sheet and follow-up "
                "about CoachLenz. See the Privacy Policy.")

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_PHONE_CHARS = re.compile(r"^[0-9+()\-.\s]+$")


class HalftimePdfLeadIn(BaseModel):
    # Length caps so a public, unauthenticated form can't be used to bloat storage.
    name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=254)
    phone: Optional[str] = Field(default=None, max_length=32)
    consent: bool = False
    # Honeypot: hidden from people, filled by naive bots. Must arrive empty.
    website: Optional[str] = Field(default=None, max_length=500)


def clean_name(raw: str) -> str:
    name = _CTRL.sub("", raw or "").strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        raise HTTPException(status_code=400, detail="Enter your name.")
    low = name.lower()
    if "http://" in low or "https://" in low or "www." in low or "<" in name or ">" in name:
        raise HTTPException(status_code=400, detail="Enter your name.")
    return name


def clean_phone(raw: Optional[str]) -> Optional[str]:
    """Optional. Blank -> None. Otherwise 7-15 digits with common separators."""
    phone = _CTRL.sub("", raw or "").strip()
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not _PHONE_CHARS.match(phone) or not (7 <= len(digits) <= 15):
        raise HTTPException(status_code=400,
                            detail="Phone is optional. Leave it blank or enter a valid number.")
    return phone


def _download_path(token: str) -> str:
    return DOWNLOAD_PATH.format(token=token)


@router.post("/halftime-pdf")
@limiter.limit("5/minute;30/hour")
async def capture_halftime_pdf_lead(body: HalftimePdfLeadIn, request: Request,
                                    db: AsyncSession = Depends(get_db)):
    """Store a validated lead and return the PDF download link."""
    # Honeypot tripped: answer like a success so the bot learns nothing, store nothing,
    # and hand out no link.
    if (body.website or "").strip():
        return {"ok": True, "download_path": None}

    name = clean_name(body.name)
    try:
        email = await validate_lead_email(body.email)
    except EmailRejected as e:
        raise HTTPException(status_code=400, detail=str(e))
    phone = clean_phone(body.phone)
    if not body.consent:
        raise HTTPException(status_code=400,
                            detail="Please check the box to agree to email follow-up.")

    ip = request.client.host if request.client else None
    ua = (request.headers.get("user-agent") or "")[:300] or None
    now = datetime.utcnow()

    async def _existing():
        res = await db.execute(select(LeadMagnetLead).where(
            func.lower(LeadMagnetLead.email) == email, LeadMagnetLead.source == SOURCE))
        return res.scalar_one_or_none()

    lead = await _existing()
    if lead is None:
        lead = LeadMagnetLead(
            source=SOURCE, name=name, email=email, phone=phone,
            consent_email=True, consent_text=CONSENT_TEXT,
            download_token=secrets.token_urlsafe(24),
            ip_address=ip, user_agent=ua, created_at=now, updated_at=now,
        )
        db.add(lead)
        try:
            await db.commit()
        except IntegrityError:
            # Same email submitted twice at once: the unique index kept one row.
            await db.rollback()
            lead = await _existing()
            if lead is None:
                raise
    else:
        # Repeat submission: refresh the row, keep the original timestamp and link.
        lead.name = name
        if phone:
            lead.phone = phone
        lead.consent_email = True
        lead.consent_text = CONSENT_TEXT
        lead.ip_address = ip
        lead.user_agent = ua
        lead.updated_at = now
        await db.commit()

    return {"ok": True, "download_path": _download_path(lead.download_token)}


@router.get("/halftime-pdf/download/{token}")
@limiter.limit("30/minute")
async def download_halftime_pdf(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The printable Halftime Sheet, for a token issued by the form above."""
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail="Download link not found")
    res = await db.execute(select(LeadMagnetLead.id).where(
        LeadMagnetLead.download_token == token, LeadMagnetLead.source == SOURCE))
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Download link not found")
    return Response(
        content=halftime_sheet_pdf(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{PDF_FILENAME}"',
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex",
        },
    )
