"""Double opt-in and the Resend handoff for the waitlist.

WAITLIST_EMAIL_ENABLED defaults off. While it is off this module returns
before any gateway method, so Resend is not called. The From address is
WAITLIST_FROM_EMAIL and has no built-in mailbox.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta

from backend.config import settings
from backend.models.marketing_consent import EmailSuppression, MarketingConsentEvent
from backend.services.waitlist_capture import active_consent, canonical_role_branch

COACHLENZ_TOPIC = "CoachLenz updates"
# Record of every confirmed contact, minors included. Never a broadcast audience.
ALL_CONFIRMED = "CoachLenz Waitlist (all confirmed)"
COACHLENZ_SEGMENT = ALL_CONFIRMED
HOLDING_COACHES = "CL Holding: Coaches"
HOLDING_COACHES_FOOTBALL = "CL Holding: Coaches Football"
HOLDING_ADMIN = "CL Holding: Admin"
LAUNCH_GENERAL = "CL Launch only: General"
MINOR_SEGMENT = "CL Launch only: Minor track"
L2_SEGMENT = "CL Launch: L2 no account"
# The live Resend account already has a segment with this exact name. Do not use it.
FORBIDDEN_SEGMENT = "General"
HOLDING_SEGMENTS = (HOLDING_COACHES, HOLDING_COACHES_FOOTBALL, HOLDING_ADMIN)
L1_SEGMENTS = HOLDING_SEGMENTS + (LAUNCH_GENERAL,)
# Older name kept so a delayed check still recognizes it.
NURTURE_SEGMENTS = HOLDING_SEGMENTS
logger = logging.getLogger(__name__)
PRIVACY_URL = "https://app.coachlenz.com/privacy"
WAITLIST_ENTITY = "Cosby AI Solutions LLC"
WAITLIST_POSTAL_ADDRESS = "1036 Highway 72 East #1020, Athens, AL 35611"
DEFAULT_WAITLIST_FROM = "Jay Cosby, CoachLenz <support@coachlenz.com>"
DEFAULT_WAITLIST_REPLY_TO = "support@coachlenz.com"
_PLACEHOLDER_MARKS = ("[POSTAL ADDRESS", "[LEGAL ENTITY", "[CITY]", "[ZIP]", "[VALID POSTAL")
TEMPLATE_C1 = "C1"
TEMPLATE_L1M = "L1-M"
CONFIRM_DAYS = 7
REMINDER_AFTER = timedelta(hours=48)
PENDING_TTL = timedelta(days=7)
MAGNET_NAME = "[LEAD MAGNET NAME]"

# Tests replace this. The default gateway is the only place that would talk to Resend.
_gateway = None


class ResendGateway:
    """Live gateway. Not used in tests. Refuses to run unless the flag and From are set."""

    def send(self, payload: dict) -> dict:
        if not emails_enabled():
            return {}
        refuse_if_placeholder(payload.get("text") or "")
        scrubbed = scrub_resend_payload(payload)
        import resend
        resend.api_key = settings.RESEND_API_KEY
        return resend.Emails.send(scrubbed) or {}

    def upsert_contact(self, email: str, properties: dict) -> None:
        if not emails_enabled():
            return
        # Contact upsert is intentionally not called from tests. A live call
        # belongs here only after Jason creates the audience by hand.
        raise RuntimeError("Live Resend contact upsert is not wired in this build.")

    def subscribe_topic(self, email: str) -> None:
        if not emails_enabled():
            return
        raise RuntimeError("Live Resend topic subscribe is not wired in this build.")

    def add_to_segment(self, email: str, segment: str) -> None:
        if not emails_enabled():
            return
        if segment == FORBIDDEN_SEGMENT:
            raise RuntimeError('Refusing the Resend segment named "General".')
        raise RuntimeError("Live Resend segment add is not wired in this build.")

    def remove_from_segment(self, email: str, segment: str) -> None:
        if not emails_enabled():
            return
        raise RuntimeError("Live Resend segment remove is not wired in this build.")

    def send_event(self, name: str, email: str, properties: dict) -> None:
        if not emails_enabled():
            return
        raise RuntimeError("Live Resend event send is not wired in this build.")

    def unsubscribe_contact(self, email: str, only_list: str) -> None:
        if not emails_enabled():
            return
        if only_list != COACHLENZ_TOPIC:
            raise RuntimeError("Refusing to touch a list that is not CoachLenz updates.")
        raise RuntimeError("Live Resend unsubscribe is not wired in this build.")


def gateway():
    return _gateway if _gateway is not None else ResendGateway()


def set_gateway(obj) -> None:
    global _gateway
    _gateway = obj


def is_minor_track(lead) -> bool:
    """minor_track is set only by reclassification."""
    return canonical_role_branch(getattr(lead, "role_branch", None)) == "minor_track"


def is_minor_contact(lead) -> bool:
    """True when role_branch is minor_track."""
    if lead is None:
        return False
    if canonical_role_branch(getattr(lead, "role_branch", None)) == "minor_track":
        return True
    return is_minor_track(lead)


def destination_segment(lead) -> str:
    branch = canonical_role_branch(getattr(lead, "role_branch", None))
    sport = (getattr(lead, "sport", None) or "").lower()
    if branch == "coach":
        return HOLDING_COACHES_FOOTBALL if sport == "football" else HOLDING_COACHES
    if branch == "admin":
        return HOLDING_ADMIN
    if branch == "minor_track":
        return MINOR_SEGMENT
    return LAUNCH_GENERAL


def path_name(lead) -> str:
    branch = canonical_role_branch(getattr(lead, "role_branch", None))
    if branch == "coach":
        return "A"
    if branch == "admin":
        return "B"
    return branch or "general"


def confirmed_event_properties(lead) -> dict:
    branch = canonical_role_branch(getattr(lead, "role_branch", None)) or "general"
    props = {"role_branch": branch}
    if branch == "coach" and (getattr(lead, "sport", None) or "").lower() == "football":
        props["sport"] = "football"
    return props


def guard_broadcast(segment: str, kind: str) -> None:
    if segment == FORBIDDEN_SEGMENT:
        raise RuntimeError('Refusing the Resend segment named "General".')
    if segment == ALL_CONFIRMED:
        raise RuntimeError(
            "CoachLenz Waitlist (all confirmed) is a record of confirmed contacts, not a broadcast audience."
        )
    if kind == "L1" and segment not in L1_SEGMENTS:
        raise RuntimeError(f"L1 cannot broadcast to {segment}.")
    if kind == "L1-M" and segment != MINOR_SEGMENT:
        raise RuntimeError("L1-M broadcasts only to CL Launch only: Minor track.")
    if kind == "L2" and segment != L2_SEGMENT:
        raise RuntimeError("L2 broadcasts only to CL Launch: L2 no account.")


def drop_delayed(lead, kind: str) -> bool:
    """End a delayed path when the contact is on the minor track.

    L1-M is the minor-track launch broadcast, so that kind is not dropped here.
    """
    if kind == "l1m":
        return False
    branch = canonical_role_branch(getattr(lead, "role_branch", None))
    return branch == "minor_track" or is_minor_track(lead)


def l1m_text() -> str:
    return (
        "CoachLenz is opening for school basketball and football game film. "
        "This is a launch notice only.\n\n"
        + standard_footer()
    )


def footer_has_placeholder(text: str) -> bool:
    return any(mark in (text or "") for mark in _PLACEHOLDER_MARKS)


def refuse_if_placeholder(text: str) -> None:
    if footer_has_placeholder(text):
        raise RuntimeError("Refusing to send while the footer still has a placeholder address.")


def scrub_resend_payload(payload: dict) -> dict:
    """IP address and user agent never go to Resend."""
    blocked = {"ip", "ip_address", "user_agent", "ua"}
    return {key: value for key, value in payload.items() if key.lower() not in blocked}


def emails_enabled() -> bool:
    sender = (os.getenv("WAITLIST_FROM") or settings.WAITLIST_FROM_EMAIL or DEFAULT_WAITLIST_FROM).strip()
    return bool(settings.WAITLIST_EMAIL_ENABLED and sender)


def email_sha256(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clip_ua(ua: str | None) -> str:
    return (ua or "")[:300]


def _event(lead, event_type: str, meta: dict, **extra) -> MarketingConsentEvent:
    pair = active_consent()
    ip = (meta.get("ip") or "").strip()
    ua = _clip_ua(meta.get("ua"))
    if event_type in ("signup", "doi_confirmed") and (not ip or not ua):
        raise ValueError("signup and confirm consent rows require ip_address and user_agent")
    return MarketingConsentEvent(
        lead_id=getattr(lead, "id", None),
        event_type=event_type,
        occurred_at=meta.get("now") or datetime.utcnow(),
        email=(lead.email or "").lower(),
        consent_text=pair["text"],
        consent_version=pair["version"],
        consent_text_sha256=pair["sha256"],
        page_url=meta.get("page_url"),
        form_id=meta.get("form_id") or "waitlist",
        utm_source=getattr(lead, "utm_source", None),
        utm_medium=getattr(lead, "utm_medium", None),
        utm_campaign=getattr(lead, "utm_campaign", None),
        utm_content=getattr(lead, "utm_content", None),
        utm_term=getattr(lead, "utm_term", None),
        referrer=getattr(lead, "referrer", None),
        role=getattr(lead, "role", None),
        ip_address=ip or None,
        user_agent=ua or None,
        **extra,
    )


def standard_footer() -> str:
    return (
        "You're getting this because you joined the CoachLenz waitlist at coachlenz.com.\n"
        f"CoachLenz is a product of {WAITLIST_ENTITY}, {WAITLIST_POSTAL_ADDRESS}.\n"
        "Unsubscribe from CoachLenz emails with one click. It's free, and you don't need to sign in.\n"
        f"Privacy Policy: {PRIVACY_URL} | Questions? Reply to this email or write to privacy@coachlenz.com."
    )


def confirmation_footer() -> str:
    return (
        "Someone entered this address on the CoachLenz waitlist at coachlenz.com. "
        "If that wasn't you, ignore this email and you won't hear from us again.\n"
        f"{WAITLIST_ENTITY}, {WAITLIST_POSTAL_ADDRESS}. Privacy Policy: {PRIVACY_URL}"
    )


def _headers(token: str) -> dict:
    link = f"https://app.coachlenz.com/waitlist/confirm?unsubscribe={token}"
    reply = (settings.WAITLIST_REPLY_TO or "").strip()
    mailto = f"<mailto:{reply}?subject=unsubscribe>" if reply else ""
    value = f"<{link}>" + (f", {mailto}" if mailto else "")
    return {
        "List-Unsubscribe": value,
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _from_address() -> str:
    # WAITLIST_FROM overrides the setting so a mailbox is never taken from RESEND_DOMAIN.
    return (os.getenv("WAITLIST_FROM") or settings.WAITLIST_FROM_EMAIL or DEFAULT_WAITLIST_FROM).strip()


def _reply_to() -> str:
    return (os.getenv("WAITLIST_REPLY_TO") or settings.WAITLIST_REPLY_TO or DEFAULT_WAITLIST_REPLY_TO).strip()


def contact_properties(lead) -> dict:
    return {
        "role": lead.role,
        "role_branch": lead.role_branch,
        "sport": lead.sport,
        "school": lead.school,
        "source": lead.source,
        "lead_magnet": lead.lead_magnet,
        "consent_version": active_consent()["version"],
        "signup_at": getattr(lead, "created_at", None),
        "confirmed_at": lead.confirmed_at,
        "has_account": bool(getattr(lead, "has_account", False)),
        "utm_source": lead.utm_source,
        "utm_medium": lead.utm_medium,
        "utm_campaign": lead.utm_campaign,
        "utm_content": lead.utm_content,
        "utm_term": lead.utm_term,
    }


async def after_stored(db, lead, meta: dict | None = None) -> str:
    """Send C0 only when email is enabled. Otherwise return before any gateway call.

    A confirmed lead who submits again gets no new C0 and no second C1.
    An unsubscribed lead who submits again is a fresh opt-in and gets one C0.
    Under-19 players get this same C0. C1 and L1-M wait until they confirm.
    """
    meta = meta or {}
    if not emails_enabled():
        return "stored_no_email"
    if lead is None or not getattr(lead, "role", None):
        return "skipped"
    now = meta.get("now") or datetime.utcnow()
    if getattr(lead, "confirmed_at", None) and not getattr(lead, "unsubscribed_at", None):
        return "already_confirmed"
    if getattr(lead, "unsubscribed_at", None):
        lead.unsubscribed_at = None
        lead.confirmed_at = None
        lead.confirm_sent_at = None
        lead.confirm_token_hash = None
        lead.a1_sent_at = None
        lead.l1m_sent_at = None
    elif getattr(lead, "confirm_sent_at", None):
        return "c0_already_sent"
    token = secrets.token_urlsafe(32)
    lead.confirm_token_hash = token_hash(token)
    lead.confirm_sent_at = now
    payload = {
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "Confirm your CoachLenz waitlist spot",
        "text": (
            "Tap the confirm button to join the CoachLenz waitlist. "
            "This link works once and expires in 7 days.\n"
            f"https://app.coachlenz.com/waitlist/confirm?token={token}\n\n"
            + confirmation_footer()
        ),
        "headers": _headers(getattr(lead, "unsubscribe_token", "") or ""),
        "kind": "C0",
    }
    result = gateway().send(payload) or {}
    db.add(_event(lead, "signup", meta, doi_sent_at=now, resend_message_id=result.get("id")))
    return "c0_sent"


def _send_c1(lead, now) -> None:
    """PDF delivery. Same note for every confirmed lead. Not sent before confirm."""
    if getattr(lead, "a1_sent_at", None):
        return
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": f"Your free {MAGNET_NAME}",
        "text": f"Your free {MAGNET_NAME} is ready.\n\n" + standard_footer(),
        "headers": _headers(getattr(lead, "unsubscribe_token", "") or ""),
        "kind": TEMPLATE_C1,
        "template_key": TEMPLATE_C1,
    })
    lead.a1_sent_at = now


async def confirm_token(db, lead, meta: dict | None = None) -> str:
    """Single-use confirm. C1 goes out only after this. A second click does not send it again."""
    meta = meta or {}
    now = meta.get("now") or datetime.utcnow()
    if lead is None:
        return "missing"
    if not emails_enabled():
        return "email_off"
    sent = getattr(lead, "confirm_sent_at", None)
    if sent and now > sent + timedelta(days=CONFIRM_DAYS) and not lead.confirmed_at:
        return "expired"
    if getattr(lead, "confirmed_at", None):
        return "already_confirmed"
    lead.confirmed_at = now
    lead.confirm_token_hash = None
    db.add(_event(
        lead, "doi_confirmed", meta,
        doi_sent_at=sent, doi_confirmed_at=now,
    ))
    gw = gateway()
    gw.upsert_contact(lead.email, contact_properties(lead))
    # Record only. This segment is never a broadcast audience.
    gw.add_to_segment(lead.email, ALL_CONFIRMED)
    gw.add_to_segment(lead.email, destination_segment(lead))
    gw.send_event("coachlenz.waitlist.confirmed", lead.email, confirmed_event_properties(lead))
    branch = canonical_role_branch(getattr(lead, "role_branch", None))
    if branch in ("general", "minor_track"):
        _send_c1(lead, now)
    return "confirmed"


async def send_launch_notice(db, lead, now: datetime | None = None) -> str:
    """L1-M, launch only, and only after the minor-track lead has confirmed."""
    if not emails_enabled():
        return "email_off"
    if lead is None or not is_minor_track(lead):
        return "not_minor"
    if not getattr(lead, "confirmed_at", None) or getattr(lead, "unsubscribed_at", None):
        return "unconfirmed"
    if getattr(lead, "l1m_sent_at", None):
        return "l1m_already_sent"
    now = now or datetime.utcnow()
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "CoachLenz is opening",
        "text": l1m_text(),
        "headers": _headers(getattr(lead, "unsubscribe_token", "") or ""),
        "kind": TEMPLATE_L1M,
        "template_key": TEMPLATE_L1M,
        "segment": MINOR_SEGMENT,
    })
    lead.l1m_sent_at = now
    return "l1m_sent"


def reminder_due(lead, now: datetime) -> bool:
    sent = getattr(lead, "confirm_sent_at", None)
    if not sent or getattr(lead, "confirmed_at", None) or getattr(lead, "unsubscribed_at", None):
        return False
    if getattr(lead, "reminder_sent_at", None):
        return False
    return now >= sent + REMINDER_AFTER


async def send_nurture_step(db, lead, step: str = "n1") -> str:
    if not emails_enabled():
        return "email_off"
    if drop_delayed(lead, "nurture"):
        return "exited"
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "A coaching note from CoachLenz",
        "text": "A coaching note.\n\n" + standard_footer(),
        "kind": "nurture",
        "step": step,
    })
    return "sent"


def broadcast(kind: str, segment: str) -> str:
    """Code-only send. Callers must not invoke this from a request. The guard runs first."""
    guard_broadcast(segment, kind)
    if not emails_enabled():
        return "email_off"
    gateway().send({
        "kind": kind,
        "segment": segment,
        "broadcast": True,
        "text": l1m_text() if kind == "L1-M" else "CoachLenz is opening.\n\n" + standard_footer(),
    })
    return "sent"


def broadcast_l1() -> list:
    """One L1 broadcast per adult segment. Never all-confirmed and never the minor track."""
    return [(segment, broadcast("L1", segment)) for segment in L1_SEGMENTS]


def broadcast_l1m() -> str:
    return broadcast("L1-M", MINOR_SEGMENT)


def broadcast_l2() -> str:
    return broadcast("L2", L2_SEGMENT)


def _gateway_members() -> dict:
    book = getattr(gateway(), "members", None)
    return book if isinstance(book, dict) else {}


def rebuild_l2(leads, suppressed=(), dry_run: bool = False) -> dict:
    """Rebuild CL Launch: L2 no account from the three holding segments.

    Does not add or remove anyone from those holding segments. dry_run returns
    counts and writes nothing. A second run with the same inputs is a no-op.
    """
    book = _gateway_members()
    holding_before = {seg: set(book.get(seg, ())) for seg in HOLDING_SEGMENTS}
    union = set()
    for seg in HOLDING_SEGMENTS:
        union |= {str(email).lower() for email in book.get(seg, ())}
    by_email = {(getattr(lead, "email", None) or "").lower(): lead for lead in leads}
    blocked = {str(email).lower() for email in suppressed}
    for email, lead in by_email.items():
        if canonical_role_branch(getattr(lead, "role_branch", None)) == "minor_track":
            blocked.add(email)
        if getattr(lead, "has_account", False):
            blocked.add(email)
    desired = union - blocked
    current = {str(email).lower() for email in book.get(L2_SEGMENT, ())}
    to_add = desired - current
    to_remove = current - desired
    result = {
        "members": len(desired),
        "add": len(to_add),
        "remove": len(to_remove),
        "noop": not to_add and not to_remove,
    }
    if dry_run or result["noop"]:
        return result
    gw = gateway()
    for email in sorted(to_remove):
        gw.remove_from_segment(email, L2_SEGMENT)
    for email in sorted(to_add):
        gw.add_to_segment(email, L2_SEGMENT)
    after = {seg: set(book.get(seg, ())) for seg in HOLDING_SEGMENTS}
    if after != holding_before:
        raise RuntimeError("L2 rebuild must not change the holding segments.")
    return result


async def send_general_launch(db, lead) -> str:
    if not emails_enabled():
        return "email_off"
    if drop_delayed(lead, "launch"):
        return "exited"
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "CoachLenz is opening",
        "text": "CoachLenz is opening.\n\n" + standard_footer(),
        "kind": "general_launch",
        "segment": GENERAL_LAUNCH,
    })
    return "sent"


async def reclassify_as_minor(db, lead) -> str:
    """Move a contact onto the minor segment. A second call changes nothing."""
    if lead is None:
        return "missing"
    if getattr(lead, "minor_reclass_at", None):
        return "noop"
    lead.role_branch = "minor_track"
    removed = list(HOLDING_SEGMENTS) + [LAUNCH_GENERAL]
    gw = gateway()
    for segment in removed:
        gw.remove_from_segment(lead.email, segment)
    gw.add_to_segment(lead.email, MINOR_SEGMENT)
    now = datetime.utcnow()
    lead.minor_reclass_at = now
    entry = {
        "email": (lead.email or "").lower(),
        "removed": removed,
        "added": MINOR_SEGMENT,
        "at": now.isoformat(),
    }
    lead.reclass_log = [entry]
    logger.info("waitlist reclassified %s onto %s", entry["email"], MINOR_SEGMENT)
    return "reclassified"


async def send_reminder(db, lead, now: datetime) -> str:
    if not emails_enabled():
        return "email_off"
    if drop_delayed(lead, "reminder"):
        return "exited"
    if not reminder_due(lead, now):
        return "not_due"
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "Still want on the CoachLenz waitlist?",
        "text": "Your confirm link is still open.\n\n" + confirmation_footer(),
        "headers": _headers(getattr(lead, "unsubscribe_token", "") or ""),
        "kind": "reminder",
    })
    lead.reminder_sent_at = now
    return "reminded"


async def unsubscribe_lead(db, lead, method: str = "unsubscribe_link") -> str:
    if lead is None:
        return "missing"
    now = datetime.utcnow()
    if not getattr(lead, "unsubscribed_at", None):
        lead.unsubscribed_at = now
    db.add(_event(lead, "unsubscribed", {"now": now}, unsubscribe_method=method))
    db.add(EmailSuppression(
        email_sha256=email_sha256(lead.email),
        suppressed_at=now,
        reason=method,
    ))
    await redact_consent_network(db, lead.email)
    if emails_enabled():
        gateway().unsubscribe_contact(lead.email, COACHLENZ_TOPIC)
    return "unsubscribed"


async def redact_consent_network(db, email: str) -> int:
    """Remove IP and user agent from consent rows for this email. The rows stay."""
    normalized = (email or "").lower().strip()
    if not normalized:
        return 0
    cleared = 0
    for obj in getattr(db, "added", []) or []:
        if getattr(obj, "email", None) == normalized and hasattr(obj, "ip_address"):
            obj.ip_address = None
            obj.user_agent = None
            cleared += 1
    try:
        from sqlalchemy import update
        await db.execute(
            update(MarketingConsentEvent)
            .where(MarketingConsentEvent.email == normalized)
            .values(ip_address=None, user_agent=None)
        )
    except Exception:
        pass
    return cleared


def is_stale_pending(lead, now: datetime) -> bool:
    created = getattr(lead, "created_at", None)
    if not created or getattr(lead, "confirmed_at", None):
        return False
    return now >= created + PENDING_TTL
