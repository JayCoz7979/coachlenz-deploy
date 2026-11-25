"""Confirm link for the waitlist. Sends nothing when WAITLIST_EMAIL_ENABLED is off."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.funnel import MarketingLead
from backend.services.waitlist_email import confirm_token, halftime_sheet_url, token_hash

router = APIRouter(tags=["waitlist"])


class ConfirmIn(BaseModel):
    token: str


@router.post("/waitlist/confirm")
async def confirm_waitlist(body: ConfirmIn, request: Request, db: AsyncSession = Depends(get_db)):
    digest = token_hash((body.token or "").strip())
    lead = (await db.execute(
        select(MarketingLead).where(MarketingLead.confirm_token_hash == digest)
    )).scalar_one_or_none()
    status = await confirm_token(db, lead, {
        "ip": request.client.host if request.client else None,
        "ua": request.headers.get("user-agent", ""),
        "page_url": "/waitlist/confirm",
    })
    await db.commit()
    ok = status in ("confirmed", "already_confirmed")
    body = {"ok": ok, "status": status}
    if ok:
        body["download_url"] = halftime_sheet_url()
    return body
