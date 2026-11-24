"""Waitlist field rules. This module does not send email and does not call Resend.

The canonical source strings, the role enum, and the consent sentence live here
so the form, the API, and a later consent log share one version.
"""
import hashlib
from datetime import datetime

from sqlalchemy import func, select

# The sentence above the Join button. Version cl-waitlist-v1. There is no checkbox.
CONSENT_TEXT = (
    "By joining, you agree that CoachLenz can email you about the waitlist, "
    "free coaching resources, launch news, and pricing when we open. "
    "You can unsubscribe anytime with one click. See our Privacy Policy."
)
CONSENT_TEXT_VERSION = "cl-waitlist-v1"

# Exact stored values. Labels are for the select only.
WAITLIST_ROLES = (
    "head_coach",
    "assistant_coach",
    "athletic_director",
    "principal_admin",
    "video_coordinator",
    "parent",
    "player",
    "other",
)

ROLE_LABELS = {
    "head_coach": "Head Coach",
    "assistant_coach": "Assistant Coach",
    "athletic_director": "Athletic Director",
    "principal_admin": "Principal or Admin",
    "video_coordinator": "Video Coordinator",
    "parent": "Parent",
    "player": "Player",
    "other": "Other",
}

# Aliases the current app used, plus the spec's names. Anything else that is a
# short tag is kept as a channel tag.
SOURCE_ALIASES = {
    "app-home": "coachlenz-app-waitlist",
    "app-onboarding": "coachlenz-app-waitlist",
    "app-waitlist": "coachlenz-app-waitlist",
    "waitlist": "coachlenz-app-waitlist",
    "marketing-site": "coachlenz-site-waitlist",
    "coachlenz-app-waitlist": "coachlenz-app-waitlist",
    "coachlenz-site-waitlist": "coachlenz-site-waitlist",
    "film-time-calculator": "film-time-calculator",
    "landing": "landing",
}

FULL_WAITLIST_SOURCES = frozenset({
    "coachlenz-app-waitlist",
    "coachlenz-site-waitlist",
})

# Filled on a repeat only when the stored value is still empty.
_FILL_IF_BLANK = (
    "first_name", "school", "sport", "role", "lead_magnet",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "referrer", "landing_path", "ref_code",
)


def canonicalize_source(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "landing"
    if s in SOURCE_ALIASES:
        return SOURCE_ALIASES[s]
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in s)
    cleaned = cleaned.strip("-")[:120]
    return cleaned or "landing"


def role_branch_for(role: str | None) -> str | None:
    if role in ("head_coach", "assistant_coach", "video_coordinator"):
        return "coach"
    if role in ("athletic_director", "principal_admin"):
        return "admin"
    if role == "player":
        return "player_hold"
    if role in ("parent", "other"):
        return "general"
    return None


def consent_text_sha256() -> str:
    return hashlib.sha256(CONSENT_TEXT.encode("utf-8")).hexdigest()


def nurture_eligible(row) -> bool:
    """Consent, confirmed, and not a player hold. Unsubscribed is not eligible."""
    if getattr(row, "unsubscribed_at", None):
        return False
    return bool(
        getattr(row, "marketing_consent", False)
        and getattr(row, "confirmed_at", None)
        and getattr(row, "role_branch", None) != "player_hold"
    )


def is_minor_player(role: str | None, is_adult: bool | None) -> bool:
    return role == "player" and is_adult is not True


def apply_repeat(row, body, source: str) -> None:
    """Fill empty columns only. Never blank a value, never downgrade consent,
    never touch confirm or unsubscribe state."""
    if not getattr(row, "source", None) and source:
        row.source = source
    for field in _FILL_IF_BLANK:
        incoming = getattr(body, field, None)
        if incoming and not getattr(row, field, None):
            setattr(row, field, incoming)
    if getattr(row, "role", None) and not getattr(row, "role_branch", None):
        row.role_branch = role_branch_for(row.role)
    if body.role == "player" and getattr(row, "is_adult", None) is None and body.is_adult is True:
        row.is_adult = True
    # Joining is the consent. Never clear a version already stored.
    if not getattr(row, "consent_text_version", None) and body.role:
        row.consent_text_version = CONSENT_TEXT_VERSION


def new_lead_kwargs(email: str, source: str, body) -> dict:
    import secrets
    role = body.role
    values = {
        "email": email,
        "source": source,
        "first_name": body.first_name,
        "school": body.school,
        "sport": body.sport,
        "role": role,
        "role_branch": role_branch_for(role),
        "is_adult": True if role == "player" and body.is_adult is True else None,
        "lead_magnet": body.lead_magnet,
        "utm_source": body.utm_source,
        "utm_medium": body.utm_medium,
        "utm_campaign": body.utm_campaign,
        "utm_content": body.utm_content,
        "utm_term": body.utm_term,
        "referrer": body.referrer,
        "landing_path": body.landing_path,
        "ref_code": body.ref_code,
        "has_account": False,
        "unsubscribe_token": secrets.token_urlsafe(32),
        "consent_text_version": CONSENT_TEXT_VERSION if role else None,
    }
    return values


async def mark_lead_has_account(db, email: str) -> None:
    """When an account is created, flag the matching waitlist row. No email."""
    from backend.models.funnel import MarketingLead
    normalized = (email or "").lower().strip()
    if not normalized:
        return
    row = (await db.execute(
        select(MarketingLead).where(func.lower(MarketingLead.email) == normalized)
    )).scalar_one_or_none()
    if row is not None and not row.has_account:
        row.has_account = True
