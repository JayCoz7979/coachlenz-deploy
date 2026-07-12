"""
Phone verification via Twilio Verify (SMS OTP). Twilio stores and checks the code
itself, so nothing is persisted locally. Degrades with a clear 503 when Twilio is
not configured (so onboarding surfaces "phone verification isn't set up" instead
of a stack trace).
"""
import logging
import re
from fastapi import HTTPException

from backend.config import settings

logger = logging.getLogger(__name__)


def phone_verification_configured() -> bool:
    """True only when Twilio Verify is fully wired up. When False, phone
    verification must NOT gate onboarding — otherwise a new user can never get
    phone_verified and is trapped, unable to finish signup. Email stays the hard gate."""
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_VERIFY_SID)


def _client():
    if not phone_verification_configured():
        return None
    from twilio.rest import Client
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def normalize_phone(phone: str) -> str:
    """Best-effort E.164. A bare 10-digit US number gets a +1; anything already
    starting with + is passed through; otherwise digits are prefixed with +."""
    p = (phone or "").strip()
    if p.startswith("+"):
        return "+" + re.sub(r"\D", "", p[1:])
    digits = re.sub(r"\D", "", p)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def send_sms_code(phone: str):
    client = _client()
    if not client:
        raise HTTPException(status_code=503, detail="Phone verification isn't configured yet. Contact support.")
    try:
        client.verify.v2.services(settings.TWILIO_VERIFY_SID).verifications.create(
            to=normalize_phone(phone), channel="sms"
        )
    except Exception as e:  # invalid number, unverified trial number, etc.
        # Log the upstream detail server-side; return a generic message so Twilio
        # account/config internals aren't disclosed to the caller.
        logger.warning("Twilio send failed: %s", str(e)[:300])
        raise HTTPException(status_code=400, detail="We couldn't text a code to that number. Check it and try again.")


def check_sms_code(phone: str, code: str) -> bool:
    client = _client()
    if not client:
        raise HTTPException(status_code=503, detail="Phone verification isn't configured yet. Contact support.")
    try:
        result = client.verify.v2.services(settings.TWILIO_VERIFY_SID).verification_checks.create(
            to=normalize_phone(phone), code=code
        )
    except Exception as e:
        logger.warning("Twilio verify failed: %s", str(e)[:300])
        raise HTTPException(status_code=400, detail="We couldn't verify that code. Request a new one and try again.")
    return getattr(result, "status", None) == "approved"
