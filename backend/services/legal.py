"""
Legal + COPPA/FERPA consent policy (beta-readiness P0 #2).

Two consents are captured and enforced:
  - terms / privacy: accepted per user at signup (a required checkbox).
  - student_data: a per-ORG authority attestation made before any student-athlete
    roster data is entered — the COPPA/FERPA representation.

Versions are bumped when the corresponding legal/*.md text is finalized or changed
by the attorney, which forces a fresh acceptance. They stay "-draft" until then.
This module is the enforcement scaffolding; the actual legal TEXT is the lawyer's.
"""
from fastapi import HTTPException
from sqlalchemy import select, func

from backend.models.legal import LegalAcceptance

TERMS_VERSION = "2026-07-31-draft"
PRIVACY_VERSION = "2026-07-31-draft"
STUDENT_DATA_VERSION = "2026-07-31-draft"

DOCUMENT_VERSIONS = {
    "terms": TERMS_VERSION,
    "privacy": PRIVACY_VERSION,
    "student_data": STUDENT_DATA_VERSION,
}

# The representation the org makes before entering student-athlete data. Placeholder
# copy for the attorney to finalize; bump STUDENT_DATA_VERSION when it changes.
STUDENT_DATA_ATTESTATION = (
    "I represent that I am authorized to provide student-athlete information to "
    "CoachLenz, and that the consent required to collect and use it has been "
    "obtained — for example school authorization under FERPA and COPPA's "
    "school-consent provision, or verifiable parental consent — including for any "
    "athletes under 13."
)


async def record_acceptance(db, organization_id, user_id, document: str, ip: str | None = None) -> None:
    """Log an acceptance of `document` at its current version. Caller commits."""
    if document not in DOCUMENT_VERSIONS:
        raise ValueError(f"unknown legal document: {document}")
    db.add(LegalAcceptance(
        organization_id=organization_id, user_id=user_id,
        document=document, version=DOCUMENT_VERSIONS[document], ip_address=ip,
    ))


async def has_current_acceptance(db, organization_id, document: str) -> bool:
    """True if the org has an acceptance of `document` at its CURRENT version."""
    res = await db.execute(
        select(func.count()).select_from(LegalAcceptance).where(
            LegalAcceptance.organization_id == organization_id,
            LegalAcceptance.document == document,
            LegalAcceptance.version == DOCUMENT_VERSIONS[document],
        )
    )
    return (res.scalar_one() or 0) > 0


async def assert_student_consent(db, organization_id) -> None:
    """Gate before any student-athlete roster data is created. 403s with a
    structured detail the frontend uses to prompt the one-time attestation."""
    if await has_current_acceptance(db, organization_id, "student_data"):
        return
    raise HTTPException(status_code=403, detail={
        "code": "student_consent_required",
        "message": "Confirm you have consent to provide student-athlete information before adding players.",
        "attestation": STUDENT_DATA_ATTESTATION,
        "version": STUDENT_DATA_VERSION,
    })
