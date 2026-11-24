"""Double opt-in and the Resend handoff for the waitlist.

WAITLIST_EMAIL_ENABLED defaults off. While it is off this module returns
before any gateway method, so Resend is not called. The From address is
WAITLIST_FROM_EMAIL and has no built-in mailbox.
"""
import hashlib
import json
import logging
import os
import re
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
# Every segment the code can write to. Each needs an id in WAITLIST_RESEND_SEGMENT_IDS.
ALL_SEGMENTS = (ALL_CONFIRMED,) + L1_SEGMENTS + (MINOR_SEGMENT, L2_SEGMENT)
# Older name kept so a delayed check still recognizes it.
NURTURE_SEGMENTS = HOLDING_SEGMENTS
logger = logging.getLogger(__name__)
PRIVACY_URL = "https://app.coachlenz.com/privacy"
WAITLIST_ENTITY = "Cosby AI Solutions LLC"
WAITLIST_POSTAL_ADDRESS = "1036 Highway 72 East #1020, Athens, AL 35611"
DEFAULT_WAITLIST_FROM = "Jay Cosby <support@coachlenz.com>"
DEFAULT_WAITLIST_REPLY_TO = "support@coachlenz.com"
_PLACEHOLDER_MARKS = ("[POSTAL ADDRESS", "[LEGAL ENTITY", "[CITY]", "[ZIP]", "[VALID POSTAL")
TEMPLATE_C1 = "C1"
TEMPLATE_L1M = "L1-M"
CONFIRM_DAYS = 7
REMINDER_AFTER = timedelta(hours=48)
PENDING_TTL = timedelta(days=7)
MAGNET_NAME = "Halftime Sheet"

# Tests replace this. The default gateway is the only place that would talk to Resend.
_gateway = None


RESEND_API_BASE = "https://api.resend.com"
CONFIRMED_EVENT = "coachlenz.waitlist.confirmed"
BROADCAST_UNSUBSCRIBE_TAG = "{{{RESEND_UNSUBSCRIBE_URL}}}"


def _segment_ids() -> dict:
    raw = (getattr(settings, "WAITLIST_RESEND_SEGMENT_IDS", "") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items() if str(v or "").strip()}


def resend_config_missing() -> list[str]:
    """Names of the settings the live gateway still needs. Never returns values."""
    missing = []
    if not (settings.RESEND_API_KEY or "").strip():
        missing.append("RESEND_API_KEY")
    if not (getattr(settings, "WAITLIST_RESEND_TOPIC_ID", "") or "").strip():
        missing.append("WAITLIST_RESEND_TOPIC_ID")
    ids = _segment_ids()
    absent = [name for name in ALL_SEGMENTS if name not in ids]
    if absent:
        missing.append("WAITLIST_RESEND_SEGMENT_IDS (" + ", ".join(absent) + ")")
    return missing


def _property_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return value
    return str(value)


_TOKENLESS_UNSUBSCRIBE = re.compile(r"/unsubscribe(?:/one-click)?\?token=(?![A-Za-z0-9_-])")


def refuse_if_tokenless_unsubscribe(payload: dict) -> None:
    """Last check before a send: never mail an unsubscribe link with an empty
    token, in the body or in List-Unsubscribe."""
    parts = [payload.get("text") or "", payload.get("html") or ""]
    parts += [str(v) for v in (payload.get("headers") or {}).values()]
    for part in parts:
        if _TOKENLESS_UNSUBSCRIBE.search(part):
            raise RuntimeError("Refusing to send an unsubscribe link with an empty token.")


class ResendGateway:
    """Live gateway. Not used in tests except with a mocked transport.

    Every method is a no-op while WAITLIST_EMAIL_ENABLED is off. When it is on,
    every method, including send, refuses until resend_config_missing() is
    empty, so a half-configured build sends nothing at all.
    """

    def __init__(self, transport=None):
        self._transport = transport

    def _ready(self) -> bool:
        if not emails_enabled():
            return False
        missing = resend_config_missing()
        if missing:
            raise RuntimeError("Resend is not configured for the waitlist. Missing: " + "; ".join(missing))
        return True

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        import httpx
        headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}"}
        with httpx.Client(base_url=RESEND_API_BASE, timeout=10.0, transport=self._transport) as client:
            res = client.request(method, path, json=body, headers=headers)
        if res.status_code >= 400:
            # Status and path only. The body can echo the address.
            raise RuntimeError(f"Resend {method} {path.split('/')[1]} failed with HTTP {res.status_code}")
        try:
            return res.json() or {}
        except ValueError:
            return {}

    @staticmethod
    def _contact_path(email: str) -> str:
        from urllib.parse import quote
        return "/contacts/" + quote((email or "").strip().lower(), safe="@")

    def send(self, payload: dict) -> dict:
        if not self._ready():
            return {}
        refuse_if_placeholder(payload.get("text") or "")
        refuse_if_tokenless_unsubscribe(payload)
        scrubbed = scrub_resend_payload(payload)
        import resend
        resend.api_key = settings.RESEND_API_KEY
        return resend.Emails.send(scrubbed) or {}

    def upsert_contact(self, email: str, properties: dict) -> None:
        if not self._ready():
            return
        props = {k: _property_value(v) for k, v in scrub_resend_payload(properties or {}).items() if v is not None}
        topic = settings.WAITLIST_RESEND_TOPIC_ID.strip()
        try:
            self._call("POST", "/contacts", {
                "email": (email or "").strip().lower(),
                "properties": props,
                "topics": [{"id": topic, "subscription": "opt_in"}],
            })
        except RuntimeError as exc:
            if "HTTP 409" not in str(exc) and "HTTP 422" not in str(exc):
                raise
            # Already a contact: update the properties and opt back in to the topic.
            self._call("PATCH", self._contact_path(email), {"properties": props})
            self.subscribe_topic(email)

    def subscribe_topic(self, email: str) -> None:
        if not self._ready():
            return
        self._call("PATCH", self._contact_path(email) + "/topics", {
            "topics": [{"id": settings.WAITLIST_RESEND_TOPIC_ID.strip(), "subscription": "opt_in"}],
        })

    def _segment_path(self, email: str, segment: str) -> str:
        if segment == FORBIDDEN_SEGMENT:
            raise RuntimeError('Refusing the Resend segment named "General".')
        seg_id = _segment_ids().get(segment)
        if not seg_id:
            raise RuntimeError(f"No Resend segment id configured for {segment}.")
        return self._contact_path(email) + "/segments/" + seg_id

    def add_to_segment(self, email: str, segment: str) -> None:
        if not self._ready():
            return
        self._call("POST", self._segment_path(email, segment))

    def remove_from_segment(self, email: str, segment: str) -> None:
        if not self._ready():
            return
        self._call("DELETE", self._segment_path(email, segment))

    def send_event(self, name: str, email: str, properties: dict) -> None:
        if not self._ready():
            return
        self._call("POST", "/events/send", {
            "event": name,
            "email": (email or "").strip().lower(),
            "payload": {k: _property_value(v) for k, v in scrub_resend_payload(properties or {}).items() if v is not None},
        })

    def send_broadcast(self, payload: dict) -> dict:
        """One Resend Broadcast to one segment, sent at once.

        Uses POST /broadcasts (not Emails.send), so Resend fills
        {{{RESEND_UNSUBSCRIBE_URL}}} per contact and honors the topic opt-out.
        """
        if not self._ready():
            return {}
        segment = payload.get("segment") or ""
        if segment in (FORBIDDEN_SEGMENT, ALL_CONFIRMED):
            raise RuntimeError("Refusing to broadcast to " + segment + ".")
        seg_id = _segment_ids().get(segment)
        if not seg_id:
            raise RuntimeError(f"No Resend segment id configured for {segment}.")
        text = payload.get("text") or ""
        refuse_if_placeholder(text)
        if BROADCAST_UNSUBSCRIBE_TAG not in text:
            raise RuntimeError("Refusing a broadcast without the Resend unsubscribe merge tag.")
        body = {
            "segment_id": seg_id,
            "topic_id": settings.WAITLIST_RESEND_TOPIC_ID.strip(),
            "from": payload.get("from") or _from_address(),
            "subject": payload.get("subject") or "",
            "text": text,
            "name": payload.get("name") or f"CoachLenz {payload.get('kind', '')} {segment}".strip(),
            "send": True,
        }
        reply = payload.get("reply_to")
        if reply:
            body["reply_to"] = reply
        return self._call("POST", "/broadcasts", body)

    def unsubscribe_contact(self, email: str, only_list: str) -> None:
        if not self._ready():
            return
        if only_list != COACHLENZ_TOPIC:
            raise RuntimeError("Refusing to touch a list that is not CoachLenz updates.")
        self._call("PATCH", self._contact_path(email) + "/topics", {
            "topics": [{"id": settings.WAITLIST_RESEND_TOPIC_ID.strip(), "subscription": "opt_out"}],
        })


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


def l1m_text(token: str | None = None, broadcast: bool = False) -> str:
    return (
        "CoachLenz is opening for school basketball and football game film. "
        "This is a launch notice only.\n\n"
        + standard_footer(token, broadcast)
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
    # IP is required evidence. An empty User-Agent is stored as null so the
    # consent row is still written (some clients send no User-Agent).
    if event_type in ("signup", "doi_confirmed") and not ip:
        raise ValueError("signup and confirm consent rows require ip_address")
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


def unsubscribe_url(token: str) -> str:
    """The page a person opens to unsubscribe. It posts the token to /auth/unsubscribe."""
    return f"{public_app_base()}/unsubscribe?token={token}"


def one_click_unsubscribe_url(token: str) -> str:
    """RFC 8058 target. The frontend route accepts the mail provider's POST."""
    return f"{public_app_base()}/unsubscribe/one-click?token={token}"


def _unsubscribe_line(token: str | None, broadcast: bool = False) -> str:
    from backend.services.unsubscribe_token import is_valid_unsubscribe_token
    if token and is_valid_unsubscribe_token(token):
        return f"Unsubscribe from CoachLenz emails with one click: {unsubscribe_url(token)}\n"
    if broadcast:
        # A Resend broadcast fills in this merge tag per contact.
        return "Unsubscribe from CoachLenz emails with one click: " + BROADCAST_UNSUBSCRIBE_TAG + "\n"
    reply = _reply_to() or DEFAULT_WAITLIST_REPLY_TO
    return f"Unsubscribe from CoachLenz emails: reply to this email or write to {reply} with the word unsubscribe.\n"


def standard_footer(token: str | None = None, broadcast: bool = False) -> str:
    return (
        "You're getting this because you joined the CoachLenz waitlist at coachlenz.com.\n"
        f"CoachLenz is a product of {WAITLIST_ENTITY}, {WAITLIST_POSTAL_ADDRESS}.\n"
        + _unsubscribe_line(token, broadcast)
        + "It's free, and you don't need to sign in.\n"
        f"Privacy Policy: {PRIVACY_URL} | Questions? Reply to this email or write to privacy@coachlenz.com."
    )


def confirmation_footer() -> str:
    return (
        "Someone entered this address on the CoachLenz waitlist at coachlenz.com. "
        "If that wasn't you, ignore this email and you won't hear from us again.\n"
        f"{WAITLIST_ENTITY}, {WAITLIST_POSTAL_ADDRESS}. Privacy Policy: {PRIVACY_URL}"
    )


def public_app_base() -> str:
    """Frontend origin for confirm links. The default is the production app host."""
    raw = (getattr(settings, "PUBLIC_APP_URL", None) or "https://app.coachlenz.com").strip().rstrip("/")
    return raw or "https://app.coachlenz.com"


def confirm_url(query: str) -> str:
    return f"{public_app_base()}/waitlist/confirm?{query}"


def c0_text(token: str) -> str:
    return (
        "Tap the confirm button to join the CoachLenz waitlist. "
        "This link works once and expires in 7 days.\n"
        f"{confirm_url(f'token={token}')}\n\n"
        + confirmation_footer()
    )


def c1_subject() -> str:
    return f"Your free {MAGNET_NAME}"


def halftime_sheet_url() -> str:
    """Hosted PDF. Default keeps the URL the confirm page already returns."""
    raw = (getattr(settings, "WAITLIST_HALFTIME_SHEET_URL", "") or "").strip()
    return raw or f"{public_app_base()}/waitlist/halftime-sheet.pdf"


def c1_text(token: str | None = None) -> str:
    return (
        f"Your free {MAGNET_NAME} is ready.\n"
        f"Download it here: {halftime_sheet_url()}\n\n"
        + standard_footer(token)
    )


def reminder_text() -> str:
    return "Your confirm link is still open.\n\n" + confirmation_footer()


def nurture_text(token: str | None = None, broadcast: bool = False) -> str:
    return "A coaching note.\n\n" + standard_footer(token, broadcast)


def launch_text(token: str | None = None, broadcast: bool = False) -> str:
    return "CoachLenz is opening.\n\n" + standard_footer(token, broadcast)


def rendered_waitlist_emails(token: str = "sample-token") -> list[str]:
    """Every subject and body this module can send. Used to catch leftover placeholders."""
    return [
        "Confirm your CoachLenz waitlist spot",
        c0_text(token),
        c1_subject(),
        c1_text(token),
        "Still want on the CoachLenz waitlist?",
        reminder_text(),
        "A coaching note from CoachLenz",
        nurture_text(token),
        "CoachLenz is opening",
        launch_text(token),
        l1m_text(token),
        unsubscribe_url(token),
    ]


def _lead_token(lead) -> str:
    """The lead's unsubscribe token, or "" when it is missing or not a shape
    any issuer makes. An empty token means no List-Unsubscribe header and the
    reply-to-unsubscribe footer line, never a link that ends in "token="."""
    from backend.services.unsubscribe_token import is_valid_unsubscribe_token
    token = getattr(lead, "unsubscribe_token", "") or ""
    return token if is_valid_unsubscribe_token(token) else ""


def _headers(token: str) -> dict:
    """RFC 8058 headers for a valid token. Empty (no List-Unsubscribe and no
    List-Unsubscribe-Post) when there is no usable token, because a one-click
    POST to a tokenless URL would answer 200 and unsubscribe nobody."""
    from backend.services.unsubscribe_token import is_valid_unsubscribe_token
    if not is_valid_unsubscribe_token(token):
        return {}
    link = one_click_unsubscribe_url(token)
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


async def _signup_already_recorded(db, lead) -> bool:
    """True when this email already has a signup consent row in this session or the table."""
    email = (getattr(lead, "email", None) or "").lower()
    pending = list(getattr(db, "added", []) or []) + list(getattr(db, "new", []) or [])
    for obj in pending:
        if isinstance(obj, MarketingConsentEvent) and obj.event_type == "signup" and (obj.email or "").lower() == email:
            return True
    try:
        from sqlalchemy import select
        res = await db.execute(
            select(MarketingConsentEvent.id).where(
                MarketingConsentEvent.email == email,
                MarketingConsentEvent.event_type == "signup",
            ).limit(1)
        )
    except Exception:
        return False
    getter = getattr(res, "scalar_one_or_none", None)
    if getter is None:
        return False
    return getter() is not None


async def after_stored(db, lead, meta: dict | None = None) -> str:
    """Record signup consent on every submit. Send C0 only when email is enabled.

    A confirmed lead who submits again gets no new consent row, no new C0, and no second C1.
    An unsubscribed lead who submits again is a fresh opt-in and gets one new consent row.
    Token creation and the confirmation email stay off while WAITLIST_EMAIL_ENABLED is false.
    """
    meta = meta or {}
    if lead is None or not getattr(lead, "role", None):
        return "skipped"
    now = meta.get("now") or datetime.utcnow()
    fresh_opt_in = bool(getattr(lead, "unsubscribed_at", None))
    if fresh_opt_in:
        lead.unsubscribed_at = None
        lead.confirmed_at = None
        lead.confirm_sent_at = None
        lead.confirm_token_hash = None
        lead.a1_sent_at = None
        lead.l1m_sent_at = None
    if getattr(lead, "confirmed_at", None):
        return "already_confirmed"
    event = None
    if fresh_opt_in or not await _signup_already_recorded(db, lead):
        event = _event(lead, "signup", meta)
        db.add(event)
    if not emails_enabled():
        return "stored_no_email"
    if getattr(lead, "confirm_sent_at", None):
        return "c0_already_sent"
    token = secrets.token_urlsafe(32)
    lead.confirm_token_hash = token_hash(token)
    lead.confirm_sent_at = now
    payload = {
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "Confirm your CoachLenz waitlist spot",
        "text": c0_text(token),
        "headers": _headers(_lead_token(lead)),
        "kind": "C0",
    }
    try:
        result = gateway().send(payload) or {}
    except Exception:
        # The lead and its consent row are still saved. Undo the token so a
        # later submit can send C0 again once the gateway works.
        logger.exception("waitlist C0 send failed for lead %s", getattr(lead, "id", None))
        lead.confirm_token_hash = None
        lead.confirm_sent_at = None
        return "c0_failed"
    if event is not None:
        event.doi_sent_at = now
        event.resend_message_id = result.get("id")
    return "c0_sent"


def _send_c1(lead, now) -> None:
    """PDF delivery. Same note for every confirmed lead. Not sent before confirm."""
    if getattr(lead, "a1_sent_at", None):
        return
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": c1_subject(),
        "text": c1_text(_lead_token(lead)),
        "headers": _headers(_lead_token(lead)),
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
    try:
        gw = gateway()
        gw.upsert_contact(lead.email, contact_properties(lead))
        # Record only. This segment is never a broadcast audience.
        gw.add_to_segment(lead.email, ALL_CONFIRMED)
        gw.add_to_segment(lead.email, destination_segment(lead))
        gw.send_event(CONFIRMED_EVENT, lead.email, confirmed_event_properties(lead))
        branch = canonical_role_branch(getattr(lead, "role_branch", None))
        if branch in ("general", "minor_track"):
            _send_c1(lead, now)
    except Exception:
        # The confirm and its consent row still commit. There is no automatic
        # replay yet: leads with confirmed_at set and a1_sent_at empty need a
        # manual re-sync once Resend works.
        logger.exception("waitlist Resend sync after confirm failed for lead %s", getattr(lead, "id", None))
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
        "text": l1m_text(_lead_token(lead)),
        "headers": _headers(_lead_token(lead)),
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
    if getattr(lead, "unsubscribed_at", None):
        return "unsubscribed"
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "A coaching note from CoachLenz",
        "text": nurture_text(_lead_token(lead)),
        "headers": _headers(_lead_token(lead)),
        "kind": "nurture",
        "step": step,
    })
    return "sent"


def broadcast(kind: str, segment: str) -> str:
    """Code-only send. Callers must not invoke this from a request. The guard runs first."""
    guard_broadcast(segment, kind)
    if not emails_enabled():
        return "email_off"
    gateway().send_broadcast({
        "kind": kind,
        "segment": segment,
        "broadcast": True,
        "from": _from_address(),
        "reply_to": _reply_to(),
        "subject": "CoachLenz is opening",
        "name": f"CoachLenz {kind} {segment}",
        "text": l1m_text(broadcast=True) if kind == "L1-M" else launch_text(broadcast=True),
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
    if getattr(lead, "unsubscribed_at", None):
        return "unsubscribed"
    gateway().send({
        "from": _from_address(),
        "reply_to": _reply_to(),
        "to": lead.email,
        "subject": "CoachLenz is opening",
        "text": launch_text(_lead_token(lead)),
        "headers": _headers(_lead_token(lead)),
        "kind": "general_launch",
        "segment": LAUNCH_GENERAL,
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
        "text": reminder_text(),
        "headers": _headers(_lead_token(lead)),
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
        try:
            gateway().unsubscribe_contact(lead.email, COACHLENZ_TOPIC)
        except Exception:
            # The local unsubscribe and suppression row still commit and every
            # per-lead send checks unsubscribed_at. Resend must be fixed by hand.
            logger.exception("waitlist Resend unsubscribe failed for lead %s", getattr(lead, "id", None))
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
