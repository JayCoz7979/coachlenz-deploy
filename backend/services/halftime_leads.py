"""Free printable Halftime Sheet PDF: double opt-in lead capture.

Flow (Jason, Nov 28):
  1. submit  -> validate name / email (format + MX/domain + disposable block) / optional
                phone server-side, store the lead status='pending', email a confirmation
                link carrying a single-use token that expires in 24 hours.
  2. confirm -> only a valid, unused, unexpired token flips the lead to 'confirmed'
                (confirmed_at + confirmed_ip) and only THEN is the PDF emailed (attached).
                Nothing returns or sends the PDF before this step.
  3. resend  -> an expired or used link (or just the email) gets a fresh link. Each new
                link replaces the previous token, so at most one link is live per lead.

Tokens: 32 random bytes (urlsafe). At rest we keep only HMAC-SHA256(SECRET_KEY, token)
in token_hash, so a database read cannot be turned into a working link.

No SMS anywhere: phone is optional, stored for the coach's record only, never texted.

Outbound safety lives in email_service.lead_email_allowed: unless a human sets
LEAD_EMAIL_LIVE_SEND=true, only LEAD_EMAIL_ALLOWLIST addresses receive mail.

The DB access goes through a tiny LeadStore so the flow is unit-testable without
Postgres; SqlLeadStore is the production implementation.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional, Protocol

from backend.config import settings

logger = logging.getLogger(__name__)

SOURCE = "halftime_pdf"
TOKEN_TTL = timedelta(hours=24)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_TOKEN_LEN = 200

# Shown next to the checkbox AND stored on the row, so the record shows exactly what
# the coach agreed to. Change the wording -> bump the version tag.
CONSENT_TEXT = (
    "[v1] Email me the free Halftime Sheet PDF and follow-up emails from CoachLenz. "
    "I can unsubscribe at any time. Phone is optional and is never texted."
)

GENERIC_SUBMIT_MESSAGE = (
    "Check your email. We sent a confirmation link. Click it within 24 hours and "
    "we will email you the Halftime Sheet PDF."
)

# A small, lightweight list of the most common throwaway-inbox domains. Not exhaustive
# on purpose (no network fetch, no new dependency); the double opt-in is the real guard.
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "sharklasers.com", "grr.la", "10minutemail.com", "10minutemail.net", "tempmail.com",
    "temp-mail.org", "temp-mail.io", "tempmail.net", "throwawaymail.com", "yopmail.com",
    "yopmail.net", "getnada.com", "nada.email", "dispostable.com", "trashmail.com",
    "trashmail.net", "maildrop.cc", "mailnesia.com", "mintemail.com", "fakeinbox.com",
    "emailondeck.com", "spamgourmet.com", "mohmal.com", "moakt.com", "tempail.com",
    "burnermail.io", "mailpoof.com", "inboxkitten.com", "mail.tm", "tempr.email",
    "discard.email", "spambox.us", "mytemp.email", "33mail.com", "harakirimail.com",
})


# ── errors ───────────────────────────────────────────────────────────────────
class LeadError(Exception):
    """A user-facing failure. `status` is the HTTP status, `code` a stable slug."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def detail(self) -> dict:
        return {"code": self.code, "message": self.message, **self.extra}


# ── validation ───────────────────────────────────────────────────────────────
_NAME_BAD = re.compile(r"(https?://|www\.|<|>)", re.I)
_PHONE_OK = re.compile(r"^[0-9+\-(). ]+$")


def clean_name(name: str) -> str:
    n = " ".join((name or "").split())
    if not n or len(n) > 100 or _NAME_BAD.search(n):
        raise LeadError(422, "invalid_name", "Please enter your name (up to 100 characters).")
    return n


def clean_phone(phone: Optional[str]) -> Optional[str]:
    """Optional. Kept only for the coach's record; never texted."""
    p = (phone or "").strip()
    if not p:
        return None
    digits = re.sub(r"\D", "", p)
    if not _PHONE_OK.match(p) or not (7 <= len(digits) <= 15):
        raise LeadError(422, "invalid_phone", "That phone number does not look right. It is optional, so you can leave it blank.")
    return p


def email_format(email: str) -> str:
    """Syntax check + normalisation (lower-cased). No DNS here."""
    from email_validator import EmailNotValidError, validate_email
    raw = (email or "").strip()
    if not raw or len(raw) > 254:
        raise LeadError(422, "invalid_email", "Please enter a valid email address.")
    try:
        v = validate_email(raw, check_deliverability=False)
    except EmailNotValidError:
        raise LeadError(422, "invalid_email", "Please enter a valid email address.")
    return v.normalized.lower()


Resolver = Callable[[str], Awaitable[bool]]


async def domain_accepts_mail(domain: str) -> bool:
    """True if the domain can receive mail: it has MX records (that are not a null MX,
    RFC 7505), or no MX but an A/AAAA record (implicit MX, RFC 5321). False when the
    domain does not exist or publishes nothing usable.

    A resolver outage / timeout fails OPEN (True): the double opt-in still means
    nothing is delivered until the inbox owner clicks the link, and a DNS blip should
    not lock real coaches out."""
    try:
        import dns.asyncresolver
        import dns.exception
        import dns.resolver
    except Exception:  # dnspython missing -> cannot check, fail open
        logger.warning("[halftime_leads] dnspython unavailable; MX check skipped")
        return True

    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 3.0
    try:
        answer = await resolver.resolve(domain, "MX")
        hosts = [str(r.exchange).rstrip(".") for r in answer]
        return any(h for h in hosts)  # a lone "." exchange is a null MX
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        pass
    except (dns.exception.Timeout, dns.resolver.NoNameservers):
        return True
    except Exception:
        return True
    for rtype in ("A", "AAAA"):
        try:
            await resolver.resolve(domain, rtype)
            return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            continue
        except Exception:
            return True
    return False


async def validate_email_address(email: str, resolver: Optional[Resolver] = None) -> str:
    """Format + disposable-domain + MX/domain check. Returns the normalised email."""
    resolver = resolver or domain_accepts_mail
    norm = email_format(email)
    domain = norm.rsplit("@", 1)[1]
    if domain in DISPOSABLE_DOMAINS:
        raise LeadError(422, "disposable_email", "Please use a real inbox you check. Temporary email addresses are not accepted.")
    if not await resolver(domain):
        raise LeadError(422, "email_domain_invalid", "That email domain cannot receive mail. Please check the address.")
    return norm


# ── tokens ───────────────────────────────────────────────────────────────────
def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


UNSUBSCRIBE_PURPOSE = "halftime-lead-unsubscribe:"


def unsubscribe_token(lead_id) -> str:
    """Signed, stateless one-click unsubscribe token for a lead: '<lead id>.<hmac>'.
    Nothing is stored for it; a forged or altered token fails verification."""
    lid = str(lead_id)
    sig = hmac.new(settings.SECRET_KEY.encode(), (UNSUBSCRIBE_PURPOSE + lid).encode(),
                   hashlib.sha256).hexdigest()
    return f"{lid}.{sig}"


def verify_unsubscribe_token(token: str) -> Optional[str]:
    """The lead id inside a valid unsubscribe token, or None."""
    token = (token or "").strip()
    if not token or len(token) > MAX_TOKEN_LEN or "." not in token:
        return None
    lid, sig = token.rsplit(".", 1)
    expected = unsubscribe_token(lid).rsplit(".", 1)[1]
    if not hmac.compare_digest(sig, expected):
        return None
    return lid


def confirm_url(token: str) -> str:
    base = (settings.LEAD_CONFIRM_BASE_URL or "https://app.coachlenz.com").rstrip("/")
    return f"{base}/live-tracker/halftime-sheet/confirm?token={token}"


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── storage ──────────────────────────────────────────────────────────────────
class LeadStore(Protocol):
    async def get_by_email(self, email: str): ...
    async def get_by_token_hash(self, token_hash: str): ...
    async def get_by_id(self, lead_id: str): ...
    async def add(self, lead) -> None: ...
    async def claim_token(self, lead, token_hash: str, now: datetime) -> bool: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SqlLeadStore:
    def __init__(self, db):
        self.db = db

    async def get_by_email(self, email: str):
        from sqlalchemy import func, select
        from backend.models.halftime_lead import HalftimePdfLead
        r = await self.db.execute(select(HalftimePdfLead).where(func.lower(HalftimePdfLead.email) == email.lower()))
        return r.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str):
        from sqlalchemy import select
        from backend.models.halftime_lead import HalftimePdfLead
        r = await self.db.execute(select(HalftimePdfLead).where(HalftimePdfLead.token_hash == token_hash))
        return r.scalar_one_or_none()

    async def get_by_id(self, lead_id: str):
        from sqlalchemy import select
        from backend.models.halftime_lead import HalftimePdfLead
        try:
            lid = uuid.UUID(str(lead_id))
        except (ValueError, TypeError):
            return None
        r = await self.db.execute(select(HalftimePdfLead).where(HalftimePdfLead.id == lid))
        return r.scalar_one_or_none()

    async def add(self, lead) -> None:
        self.db.add(lead)

    async def claim_token(self, lead, token_hash: str, now: datetime) -> bool:
        """Atomic single use: only one concurrent click can flip token_used_at."""
        from sqlalchemy import update
        from backend.models.halftime_lead import HalftimePdfLead
        r = await self.db.execute(
            update(HalftimePdfLead)
            .where(HalftimePdfLead.id == lead.id,
                   HalftimePdfLead.token_hash == token_hash,
                   HalftimePdfLead.token_used_at.is_(None),
                   HalftimePdfLead.token_expires_at > now)
            .values(token_used_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if r.rowcount == 1:
            lead.token_used_at = now
            return True
        return False

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()


def _new_lead(*, name: str, email: str, phone: Optional[str], ip: Optional[str], now: datetime):
    from backend.models.halftime_lead import HalftimePdfLead
    return HalftimePdfLead(
        id=uuid.uuid4(), name=name, email=email, phone=phone, source=SOURCE,
        status="pending", consent_text=CONSENT_TEXT, consented_at=now, submit_ip=ip,
        confirmation_send_count=0, created_at=now, updated_at=now,
    )


# ── outbound (patched in tests) ──────────────────────────────────────────────
async def _send_confirmation_email(to: str, name: str, url: str, unsub_token: str) -> bool:
    from backend.services import email_service
    return await email_service.send_halftime_confirm_email(to, name, url, unsub_token)


async def _send_pdf_email(to: str, name: str, unsub_token: str) -> bool:
    from backend.services import email_service
    from backend.services.halftime_pdf import PDF_FILENAME, halftime_sheet_pdf
    return await email_service.send_halftime_pdf_email(to, name, halftime_sheet_pdf(), PDF_FILENAME, unsub_token)


# ── flow ─────────────────────────────────────────────────────────────────────
@dataclass
class SendOutcome:
    sent: bool          # a new link was issued (False = cooldown skip)


async def _issue_confirmation(store: LeadStore, lead, now: datetime) -> SendOutcome:
    """Send a fresh single-use link, THEN persist its hash + expiry + cooldown marker.

    The cooldown is recorded only after a successful send (same lesson as the
    send-email-code fix): a failed send leaves no cooldown, so an immediate retry works."""
    last = _aware(lead.confirmation_sent_at)
    if last is not None and now - last < RESEND_COOLDOWN:
        return SendOutcome(sent=False)
    token = new_token()
    try:
        await _send_confirmation_email(lead.email, lead.name, confirm_url(token), unsubscribe_token(lead.id))
    except Exception as e:
        logger.warning("[halftime_leads] confirmation send failed: %s", type(e).__name__)
        raise LeadError(502, "email_send_failed", "We could not send the confirmation email right now. Please try again in a moment.")
    lead.token_hash = hash_token(token)
    lead.token_expires_at = now + TOKEN_TTL
    lead.token_used_at = None
    lead.confirmation_sent_at = now
    lead.confirmation_send_count = (lead.confirmation_send_count or 0) + 1
    lead.updated_at = now
    await store.commit()
    return SendOutcome(sent=True)


async def submit_lead(store: LeadStore, *, name: str, email: str, phone: Optional[str],
                      consent: bool, ip: Optional[str], now: Optional[datetime] = None,
                      resolver: Optional[Resolver] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not consent:
        raise LeadError(422, "consent_required", "Please tick the box so we can email you the PDF.")
    name = clean_name(name)
    phone = clean_phone(phone)
    email = await validate_email_address(email, resolver)

    lead = await store.get_by_email(email)
    if lead is None:
        lead = _new_lead(name=name, email=email, phone=phone, ip=ip, now=now)
        await store.add(lead)
        await store.commit()          # the pending lead exists even if the send fails
    elif lead.status == "unsubscribed":
        # Submitting the form again is a new, explicit request: back to pending with
        # the new consent, and still nothing but a confirmation link until they click.
        lead.status = "pending"
        lead.consent_text = CONSENT_TEXT
        lead.consented_at = now
        lead.submit_ip = ip
        lead.updated_at = now
        await store.commit()
    await _issue_confirmation(store, lead, now)
    # Same answer whether the address is new, pending, confirmed, or in cooldown.
    return {"ok": True, "status": "pending", "message": GENERIC_SUBMIT_MESSAGE}


async def confirm_lead(store: LeadStore, *, token: str, ip: Optional[str],
                       now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    token = (token or "").strip()
    if not token or len(token) > MAX_TOKEN_LEN:
        raise LeadError(400, "token_invalid", "This confirmation link is not valid. Request a new one below.", resend_available=True)
    h = hash_token(token)
    lead = await store.get_by_token_hash(h)
    if lead is None:
        raise LeadError(400, "token_invalid", "This confirmation link is not valid. Request a new one below.", resend_available=True)
    if lead.token_used_at is not None:
        raise LeadError(410, "token_used", "This confirmation link was already used. Request a new link and we will email the PDF again.",
                        resend_available=True, already_confirmed=lead.status == "confirmed")
    expires = _aware(lead.token_expires_at)
    if expires is None or expires <= now:
        raise LeadError(410, "token_expired", "This confirmation link expired (links last 24 hours). Request a new one below.",
                        resend_available=True)
    if not await store.claim_token(lead, h, now):
        # Lost a race with a concurrent click of the same link.
        raise LeadError(410, "token_used", "This confirmation link was already used. Request a new link and we will email the PDF again.",
                        resend_available=True, already_confirmed=True)
    if lead.status != "confirmed":
        lead.status = "confirmed"
        lead.confirmed_at = now
        lead.confirmed_ip = ip
    lead.updated_at = now
    await store.commit()

    # Confirmed first, PDF second: the PDF is never sent for an unconfirmed lead.
    try:
        await _send_pdf_email(lead.email, lead.name, unsubscribe_token(lead.id))
    except Exception as e:
        logger.warning("[halftime_leads] pdf send failed: %s", type(e).__name__)
        raise LeadError(502, "pdf_send_failed", "Your email is confirmed, but we could not send the PDF just now. Request a new link below to try again.",
                        resend_available=True, already_confirmed=True)
    lead.pdf_sent_at = now
    lead.updated_at = now
    await store.commit()
    return {"ok": True, "status": "confirmed",
            "message": "You are confirmed. We just emailed you the Halftime Sheet PDF."}


async def resend_confirmation(store: LeadStore, *, email: Optional[str] = None, token: Optional[str] = None,
                              now: Optional[datetime] = None) -> dict:
    """Issue a fresh link for an expired / used / lost one. Generic answer either way
    so the endpoint cannot be used to discover which addresses are on the list."""
    now = now or datetime.now(timezone.utc)
    lead = None
    tok = (token or "").strip()
    if tok and len(tok) <= MAX_TOKEN_LEN:
        lead = await store.get_by_token_hash(hash_token(tok))
    if lead is None and email:
        lead = await store.get_by_email(email_format(email))
    if lead is not None and lead.status != "unsubscribed":
        await _issue_confirmation(store, lead, now)
    return {"ok": True, "message": "If that address asked for the Halftime Sheet, a new confirmation link is on its way. It lasts 24 hours."}


UNSUBSCRIBED_MESSAGE = "You are unsubscribed. CoachLenz will not send you more Halftime Sheet emails."


async def unsubscribe_lead(store: LeadStore, *, token: str, now: Optional[datetime] = None) -> dict:
    """One-click unsubscribe (link in every lead email + List-Unsubscribe header).

    A valid signed token sets status='unsubscribed' + unsubscribed_at and kills any
    outstanding confirmation link. Idempotent: a second click, or a lead that no longer
    exists, gets the same success answer. Only a forged/garbled token is refused."""
    now = now or datetime.now(timezone.utc)
    lead_id = verify_unsubscribe_token(token)
    if lead_id is None:
        raise LeadError(400, "token_invalid", "This unsubscribe link is not valid. Open it straight from the email.")
    lead = await store.get_by_id(lead_id)
    if lead is not None and lead.status != "unsubscribed":
        lead.status = "unsubscribed"
        lead.unsubscribed_at = now
        lead.token_hash = None
        lead.token_expires_at = None
        lead.updated_at = now
        await store.commit()
    return {"ok": True, "status": "unsubscribed", "message": UNSUBSCRIBED_MESSAGE}
