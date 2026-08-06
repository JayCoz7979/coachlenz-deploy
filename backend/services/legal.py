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
from sqlalchemy.exc import IntegrityError

from backend.models.legal import LegalAcceptance

TERMS_VERSION = "2026-07-31-draft"
PRIVACY_VERSION = "2026-07-31-draft"
STUDENT_DATA_VERSION = "2026-07-31-draft"
RECRUITING_DIRECTORY_VERSION = "2026-08-05-draft"

DOCUMENT_VERSIONS = {
    "terms": TERMS_VERSION,
    "privacy": PRIVACY_VERSION,
    "student_data": STUDENT_DATA_VERSION,
    "recruiting_directory": RECRUITING_DIRECTORY_VERSION,
}

# The disclosure a coach makes before publishing a player's recruiting profile
# (name + film + stats) to third parties. Distinct from STUDENT_DATA_ATTESTATION,
# which authorizes COLLECTION, not public/third-party disclosure. Placeholder copy
# for the attorney to finalize; bump RECRUITING_DIRECTORY_VERSION when it changes.
RECRUITING_DIRECTORY_ATTESTATION = (
    "I am authorized to publish this student-athlete's recruiting information "
    "(name, film, and statistics) to college recruiters and other third parties, "
    "and the disclosure of this directory information is permitted under FERPA "
    "(with any required parental notice/opt-out honored) or by verifiable parental "
    "consent for athletes under 13."
)

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
    """Log an acceptance of `document` at its current version. Caller commits.

    Idempotent: the insert is wrapped in a savepoint so a duplicate (the accept
    flow's read-check races, or a double-click) collides with the
    uq_legal_acceptance constraint and is quietly ignored instead of accreting a
    duplicate audit row (or, once the constraint exists, failing the caller's
    commit). One authoritative row per (org, user, document, version)."""
    if document not in DOCUMENT_VERSIONS:
        raise ValueError(f"unknown legal document: {document}")
    try:
        async with db.begin_nested():
            db.add(LegalAcceptance(
                organization_id=organization_id, user_id=user_id,
                document=document, version=DOCUMENT_VERSIONS[document], ip_address=ip,
            ))
    except IntegrityError:
        pass  # already recorded at this version — idempotent


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


# Terms + Privacy are per-USER agreements (each individual accepts), unlike the
# per-ORG student_data attestation. When their version bumps, every existing user
# must re-accept — so these are checked per-user, not per-org.
RECONSENT_DOCUMENTS = ("terms", "privacy")


async def has_current_user_acceptance(db, user_id, document: str) -> bool:
    """True if THIS USER has accepted `document` at its current version."""
    res = await db.execute(
        select(func.count()).select_from(LegalAcceptance).where(
            LegalAcceptance.user_id == user_id,
            LegalAcceptance.document == document,
            LegalAcceptance.version == DOCUMENT_VERSIONS[document],
        )
    )
    return (res.scalar_one() or 0) > 0


async def user_reconsent_needed(db, user_id) -> list[str]:
    """Which per-user agreements (terms/privacy) the user must (re)accept at the
    current version. Empty = up to date; non-empty after a version bump until the
    user re-accepts. Drives the app-load re-consent modal."""
    needed = []
    for doc in RECONSENT_DOCUMENTS:
        if not await has_current_user_acceptance(db, user_id, doc):
            needed.append(doc)
    return needed


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
