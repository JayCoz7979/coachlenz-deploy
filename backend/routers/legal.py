"""
Legal consent status + the one-time student-data authority attestation.

Terms/Privacy are accepted at signup (see auth.register). This router lets the app
read consent status and lets an org roster-manager make the per-org student-data
(COPPA/FERPA) attestation that gates roster data entry.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.user import User
from backend.services.auth import get_current_user, require_permission
from backend.services.permissions import CAN_MANAGE_ROSTER
from backend.services.legal import (
    DOCUMENT_VERSIONS, STUDENT_DATA_ATTESTATION, RECONSENT_DOCUMENTS,
    has_current_acceptance, has_current_user_acceptance, record_acceptance,
    user_reconsent_needed,
)

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/status")
async def legal_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {
        "versions": DOCUMENT_VERSIONS,
        "student_data_consent": await has_current_acceptance(db, user.organization_id, "student_data"),
        "student_data_attestation": STUDENT_DATA_ATTESTATION,
        # Per-user terms/privacy the current user must re-accept after a version bump
        # (empty when up to date). Drives the app-load re-consent modal.
        "reconsent_needed": await user_reconsent_needed(db, user.id),
    }


@router.post("/accept-latest")
async def accept_latest(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record the current user's acceptance of the CURRENT Terms + Privacy versions.
    Any authenticated user re-accepts their own agreements (no special permission).
    Idempotent: only writes the ones not already current."""
    ip = request.client.host if request.client else None
    for doc in RECONSENT_DOCUMENTS:
        if not await has_current_user_acceptance(db, user.id, doc):
            await record_acceptance(db, user.organization_id, user.id, doc, ip=ip)
    await db.commit()
    return {"ok": True, "reconsent_needed": []}


@router.post("/student-consent")
async def attest_student_consent(
    request: Request,
    user: User = Depends(require_permission(CAN_MANAGE_ROSTER)),
    db: AsyncSession = Depends(get_db),
):
    """Record the per-org student-data authority attestation. Requires the same
    capability as managing the roster (head coach / coordinator / owner)."""
    ip = request.client.host if request.client else None
    await record_acceptance(db, user.organization_id, user.id, "student_data", ip=ip)
    await db.commit()
    return {"ok": True, "student_data_consent": True}
