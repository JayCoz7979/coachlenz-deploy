"""Waitlist field rules. This module does not send email and does not call Resend.

The canonical source strings, the role enum, and the consent sentence live here
so the form, the API, and a later consent log share one version.
"""
import hashlib
from datetime import datetime

from sqlalchemy import func, select

# The live form is locked to the Halftime Sheet line. Pair A stays in code and is not rendered.
# consent_text stores the sentence and the button label. cl-halftime-v1 replaces cl-waitlist-v1-b.
_LINE_A = (
    "By joining, you agree that CoachLenz can email you about the waitlist, "
    "free coaching resources, launch news, and pricing when we open. "
    "You can unsubscribe anytime with one click. See our Privacy Policy."
)
_LINE_LOCKED = (
    "By clicking Send me the Halftime Sheet, you join the CoachLenz waitlist and agree "
    "that CoachLenz can email you about the waitlist, free coaching resources, launch news, "
    "and pricing when we open. You can unsubscribe anytime with one click. See our Privacy Policy."
)
CONSENT_PAIRS = {
    "a": {
        "version": "cl-waitlist-v1-a",
        "button": "Join the waitlist",
        "line": _LINE_A,
    },
    "b": {
        "version": "cl-halftime-v1",
        "button": "Send me the Halftime Sheet",
        "line": _LINE_LOCKED,
    },
}

# Exact stored values. Labels are for the select only.
WAITLIST_ROLES = (
    "head_coach",
    "assistant_coach",
    "athletic_director",
    "principal_admin",
    "video_coordinator",
    "parent",
    "other",
)

ROLE_LABELS = {
    "head_coach": "Head Coach",
    "assistant_coach": "Assistant Coach",
    "athletic_director": "Athletic Director",
    "principal_admin": "Principal or Admin",
    "video_coordinator": "Video Coordinator",
    "parent": "Parent",
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


def canonical_role_branch(value: str | None) -> str | None:
    return value


def role_branch_for(role: str | None) -> str | None:
    if role in ("head_coach", "assistant_coach", "video_coordinator"):
        return "coach"
    if role in ("athletic_director", "principal_admin"):
        return "admin"
    # No signup role maps to minor_track. Reclassification sets that branch.
    if role in ("parent", "other"):
        return "general"
    return None


def active_pair_id() -> str:
    from backend.config import settings
    raw = (getattr(settings, "WAITLIST_CONSENT_PAIR", None) or "a").strip().lower()
    return raw if raw in CONSENT_PAIRS else "b"


def active_consent() -> dict:
    """The pair in force right now. text is the sentence plus the button label."""
    pair = CONSENT_PAIRS[active_pair_id()]
    text = pair["line"] + "\nButton: " + pair["button"]
    return {
        "id": active_pair_id(),
        "version": pair["version"],
        "button": pair["button"],
        "line": pair["line"],
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def consent_text() -> str:
    return active_consent()["text"]


def consent_version() -> str:
    return active_consent()["version"]


def consent_text_sha256() -> str:
    return active_consent()["sha256"]


def nurture_eligible(row) -> bool:
    """Consent, confirmed, and not on the minor track. Unsubscribed is not eligible."""
    if getattr(row, "unsubscribed_at", None):
        return False
    branch = canonical_role_branch(getattr(row, "role_branch", None))
    return bool(
        getattr(row, "marketing_consent", False)
        and getattr(row, "confirmed_at", None)
        and branch != "minor_track"
    )


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
    # Joining is the consent. Never clear a version already stored.
    if not getattr(row, "consent_text_version", None) and body.role:
        row.consent_text_version = consent_version()


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
        "lead_magnet": body.lead_magnet,
        "utm_source": body.utm_source,
        "utm_medium": body.utm_medium,
        "utm_campaign": body.utm_campaign,
        "utm_content": body.utm_content,
        "utm_term": body.utm_term,
        "referrer": body.referrer,
        "landing_path": body.landing_path,
        # Stored only. A ref code does not create a referral or a reward.
        "ref_code": body.ref_code,
        "has_account": False,
        "unsubscribe_token": secrets.token_urlsafe(32),
        "consent_text_version": consent_version() if role else None,
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
