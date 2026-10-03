"""
COPPA/FERPA parent data-access + deletion requests.

Public intake (no login — a parent has no account), then an admin verifies the
requester (in coordination with the school, which holds consent under the school-consent
mechanism) and fulfills it. Deletion fulfillment runs a tightly scoped erasure and emails
a Deletion Certificate. The request row is the audit trail.
"""
import html
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.user import User
from backend.models.privacy_request import PrivacyRequest
from backend.services.auth import require_admin
from backend.services import email_service
from backend.services import privacy_requests as svc
from backend.ratelimit import limiter
from backend.config import settings

router = APIRouter(tags=["privacy"])

_VALID_TYPES = {"access", "deletion"}
_VALID_REL = {"parent", "guardian", "eligible_student", "school_official", "other"}


class PrivacyRequestIn(BaseModel):
    request_type: str
    requester_name: str
    requester_email: EmailStr
    relationship: str
    student_name: str
    school_or_org: Optional[str] = None
    student_details: Optional[str] = None
    details: Optional[str] = None


@router.post("/privacy/requests")
@limiter.limit("5/minute")
async def submit_request(body: PrivacyRequestIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Public, no-login intake for a parent's data access/deletion request."""
    rtype = (body.request_type or "").strip().lower()
    rel = (body.relationship or "").strip().lower()
    if rtype not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail="request_type must be 'access' or 'deletion'")
    if rel not in _VALID_REL:
        raise HTTPException(status_code=400, detail="invalid relationship")
    if not (body.requester_name or "").strip() or not (body.student_name or "").strip():
        raise HTTPException(status_code=400, detail="requester_name and student_name are required")

    ip = request.client.host if request.client else None
    pr = PrivacyRequest(
        request_type=rtype,
        requester_name=body.requester_name.strip(),
        requester_email=str(body.requester_email).strip().lower(),
        relationship=rel,
        student_name=body.student_name.strip(),
        school_or_org=(body.school_or_org or None),
        student_details=(body.student_details or None),
        details=(body.details or None),
        status="pending",
        status_token=secrets.token_urlsafe(24),
        ip_address=ip,
    )
    db.add(pr)
    await db.commit()
    await db.refresh(pr)

    # Transactional emails: never let a send failure lose a recorded request.
    try:
        await email_service.send_privacy_request_ack(pr.requester_email, pr.requester_name, rtype, str(pr.id))
    except Exception:
        pass
    try:
        if settings.ADMIN_EMAIL:
            await email_service.send_privacy_admin_notice(settings.ADMIN_EMAIL, pr)
    except Exception:
        pass

    return {"ok": True, "reference": str(pr.id), "status_token": pr.status_token}


@router.get("/privacy/requests/{request_id}/status")
async def request_status(request_id: str, token: str, db: AsyncSession = Depends(get_db)):
    """Public status check, gated by the status_token issued at submission."""
    import uuid as _uuid
    try:
        _uuid.UUID(str(request_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Request not found")
    res = await db.execute(select(PrivacyRequest).where(PrivacyRequest.id == request_id))
    pr = res.scalar_one_or_none()
    if not pr or not token or not secrets.compare_digest(token, pr.status_token):
        raise HTTPException(status_code=404, detail="Request not found")
    return {"reference": str(pr.id), "request_type": pr.request_type, "status": pr.status,
            "submitted_at": pr.created_at.isoformat() if pr.created_at else None,
            "completed_at": pr.completed_at.isoformat() if pr.completed_at else None}


# ── Admin ───────────────────────────────────────────────────────────────────────
def _admin_out(pr: PrivacyRequest) -> dict:
    return {
        "id": str(pr.id), "request_type": pr.request_type, "status": pr.status,
        "requester_name": pr.requester_name, "requester_email": pr.requester_email,
        "relationship": pr.relationship, "student_name": pr.student_name,
        "school_or_org": pr.school_or_org, "student_details": pr.student_details,
        "details": pr.details, "resolution_note": pr.resolution_note,
        "certificate_id": pr.certificate_id,
        "organization_id": str(pr.organization_id) if pr.organization_id else None,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "verified_at": pr.verified_at.isoformat() if pr.verified_at else None,
        "completed_at": pr.completed_at.isoformat() if pr.completed_at else None,
    }


@router.get("/admin/privacy-requests")
async def list_requests(status: Optional[str] = None, user: User = Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    q = select(PrivacyRequest).order_by(PrivacyRequest.created_at.desc())
    if status:
        q = q.where(PrivacyRequest.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [_admin_out(r) for r in rows]


class VerifyIn(BaseModel):
    organization_id: Optional[str] = None
    note: Optional[str] = None


@router.post("/admin/privacy-requests/{request_id}/verify")
async def verify_request(request_id: str, body: VerifyIn, user: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    """Mark the requester's identity/authority verified (coordinated with the school) and
    attach the org the data lives in. Required before fulfillment."""
    pr = (await db.execute(select(PrivacyRequest).where(PrivacyRequest.id == request_id))).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Request not found")
    if pr.status in ("completed", "rejected"):
        raise HTTPException(status_code=409, detail=f"Request already {pr.status}")
    if body.organization_id:
        pr.organization_id = body.organization_id
    pr.status = "verified"
    pr.verified_at = datetime.utcnow()
    if body.note:
        pr.resolution_note = ((pr.resolution_note or "") + f"\n[verify] {body.note}").strip()
    await db.commit()
    return {"ok": True, "status": pr.status}


class FulfillIn(BaseModel):
    roster_player_ids: list[str] = []
    game_ids: list[str] = []
    note: Optional[str] = None


@router.post("/admin/privacy-requests/{request_id}/fulfill")
async def fulfill_request(request_id: str, body: FulfillIn, user: User = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    """Fulfill a verified request. For a deletion, runs the scoped erasure and emails a
    Deletion Certificate. For an access request, marks it completed (the admin provides
    the compiled data) and emails the requester."""
    pr = (await db.execute(select(PrivacyRequest).where(PrivacyRequest.id == request_id))).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Request not found")
    if pr.status != "verified":
        raise HTTPException(status_code=409, detail="Verify the request before fulfilling it")

    if pr.request_type == "deletion":
        if not pr.organization_id:
            raise HTTPException(status_code=400, detail="Resolve the org (verify step) before deletion")
        summary = await svc.execute_deletion(
            db, pr.organization_id, body.roster_player_ids, body.game_ids)
        cert_id = f"CL-DEL-{datetime.utcnow().strftime('%Y%m%d')}-{str(pr.id)[:8]}"
        pr.certificate_id = cert_id
        pr.status = "completed"
        pr.completed_at = datetime.utcnow()
        note = (f"deleted players={summary['players_deleted']}, "
                f"plays de-identified={summary['events_scrubbed']}, "
                f"games deleted={summary['games_deleted']}")
        if body.note:
            note += f" | {body.note}"
        pr.resolution_note = ((pr.resolution_note or "") + f"\n[fulfill] {note}").strip()
        await db.commit()
        try:
            cert_html = svc.render_certificate(certificate_id=cert_id, request=pr, summary=summary)
            await email_service.send_deletion_certificate(pr.requester_email, pr.requester_name, cert_html)
        except Exception:
            pass
        return {"ok": True, "status": pr.status, "certificate_id": cert_id, "summary": summary}

    # access request
    pr.status = "completed"
    pr.completed_at = datetime.utcnow()
    if body.note:
        pr.resolution_note = ((pr.resolution_note or "") + f"\n[fulfill] {body.note}").strip()
    await db.commit()
    try:
        await email_service.send_privacy_request_resolution(
            pr.requester_email, pr.requester_name,
            "Your CoachLenz data access request is complete",
            "<p>Your data access request has been completed. We'll provide the compiled "
            "records to you securely" + (f": {html.escape(body.note)}" if body.note else ".") + "</p>")
    except Exception:
        pass
    return {"ok": True, "status": pr.status}


class RejectIn(BaseModel):
    reason: str


@router.post("/admin/privacy-requests/{request_id}/reject")
async def reject_request(request_id: str, body: RejectIn, user: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    pr = (await db.execute(select(PrivacyRequest).where(PrivacyRequest.id == request_id))).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Request not found")
    if pr.status in ("completed", "rejected"):
        raise HTTPException(status_code=409, detail=f"Request already {pr.status}")
    pr.status = "rejected"
    pr.resolution_note = ((pr.resolution_note or "") + f"\n[reject] {body.reason}").strip()
    await db.commit()
    try:
        await email_service.send_privacy_request_resolution(
            pr.requester_email, pr.requester_name,
            "Update on your CoachLenz data request",
            f"<p>We were unable to complete your request as submitted. Reason: {html.escape(body.reason)}</p>"
            f"<p>If you believe this is in error, reply with any additional detail that helps us "
            f"verify your authority over this student's data.</p>")
    except Exception:
        pass
    return {"ok": True, "status": pr.status}
