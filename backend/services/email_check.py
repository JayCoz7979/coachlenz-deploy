"""
Server-side email validation for public lead forms.

Three checks, cheapest first:
  1. Format: email_validator (already installed via pydantic[email]) parses and
     normalizes the address. No network.
  2. Disposable domains: a small built-in blocklist of well-known throwaway inboxes
     (and their subdomains). Deliberately lightweight: no external list, no network.
  3. Domain accepts mail: an async DNS lookup. An MX record wins; with no MX, an A or
     AAAA record is accepted (RFC 5321 implicit MX). A domain that does not exist
     (NXDOMAIN), has no mail-capable records, or publishes a "null MX" (RFC 7505) is
     rejected.

DNS outage policy: if the resolver itself is unreachable or times out we cannot tell
a good domain from a bad one, so the address is ACCEPTED and a warning is logged. A
flaky resolver must not silently drop every real coach who asks for the sheet. A
domain that answers "does not exist" is always rejected.
"""
from __future__ import annotations

import logging
from typing import Optional

from email_validator import EmailNotValidError, validate_email

logger = logging.getLogger(__name__)

DNS_TIMEOUT_SECONDS = 3.0

# Well-known disposable / throwaway inbox providers. Short on purpose; extend as needed.
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "mailinator.net", "mailinator.org",
    "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamail.biz",
    "guerrillamailblock.com", "sharklasers.com", "grr.la", "pokemail.net", "spam4.me",
    "10minutemail.com", "10minutemail.net", "20minutemail.com",
    "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmail.net", "tempmailo.com",
    "tempr.email", "tempinbox.com", "throwawaymail.com", "trashmail.com", "trashmail.net",
    "trashmail.de", "yopmail.com", "yopmail.net", "yopmail.fr",
    "getnada.com", "nada.email", "dispostable.com", "maildrop.cc", "mailnesia.com",
    "mintemail.com", "mohmal.com", "emailondeck.com", "fakeinbox.com", "fakemail.net",
    "getairmail.com", "mailcatch.com", "moakt.com", "mytemp.email", "spamgourmet.com",
    "spambox.us", "discard.email", "burnermail.io", "inboxkitten.com", "1secmail.com",
    "1secmail.net", "1secmail.org", "emailfake.com", "mail.tm", "mailpoof.com",
    "harakirimail.com", "tmail.ws", "tmpmail.org", "tmpmail.net", "linshiyouxiang.net",
})


class EmailRejected(ValueError):
    """The address failed validation. str(exc) is safe to show the visitor."""


def normalize_email(raw: str) -> tuple[str, str]:
    """Format check only (no network). Returns (normalized_email, ascii_domain)."""
    raw = (raw or "").strip()
    if not raw or len(raw) > 254:
        raise EmailRejected("Enter a valid email address.")
    try:
        info = validate_email(raw, check_deliverability=False)
    except EmailNotValidError:
        raise EmailRejected("Enter a valid email address.")
    domain = (info.ascii_domain or info.domain or "").lower()
    local = info.local_part
    return f"{local}@{domain}".lower(), domain


def is_disposable(domain: str) -> bool:
    """True for a listed disposable domain or any subdomain of one."""
    d = (domain or "").lower().strip(".")
    parts = d.split(".")
    return any(".".join(parts[i:]) in DISPOSABLE_DOMAINS for i in range(len(parts) - 1))


async def _resolve(domain: str, rdtype: str):
    """One DNS query. Isolated so tests can replace it (unit tests never touch DNS)."""
    import dns.asyncresolver
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = DNS_TIMEOUT_SECONDS
    resolver.timeout = DNS_TIMEOUT_SECONDS
    return await resolver.resolve(domain, rdtype)


async def domain_accepts_mail(domain: str) -> Optional[bool]:
    """True = can receive mail, False = cannot, None = DNS unavailable (unknown)."""
    import dns.exception
    import dns.resolver

    try:
        answer = await _resolve(domain, "MX")
        exchanges = [str(getattr(r, "exchange", "")).rstrip(".") for r in answer]
        # RFC 7505 null MX: a single "." exchange means "this domain takes no mail".
        if exchanges and all(x == "" for x in exchanges):
            return False
        return bool(exchanges)
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        pass  # no MX: fall back to an address record (implicit MX)
    except (dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        logger.warning("[email_check] DNS unavailable for MX lookup on %s: %s", domain, type(e).__name__)
        return None
    except Exception as e:  # unexpected resolver failure: unknown, not "bad"
        logger.warning("[email_check] MX lookup error on %s: %s", domain, type(e).__name__)
        return None

    for rdtype in ("A", "AAAA"):
        try:
            answer = await _resolve(domain, rdtype)
            if len(list(answer)) > 0:
                return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            continue
        except (dns.resolver.NoNameservers, dns.exception.Timeout) as e:
            logger.warning("[email_check] DNS unavailable for %s lookup on %s: %s", rdtype, domain, type(e).__name__)
            return None
        except Exception as e:
            logger.warning("[email_check] %s lookup error on %s: %s", rdtype, domain, type(e).__name__)
            return None
    return False


async def validate_lead_email(raw: str) -> str:
    """Format + disposable + MX/domain. Returns the normalized address or raises
    EmailRejected with a visitor-safe message."""
    email, domain = normalize_email(raw)
    if is_disposable(domain):
        raise EmailRejected("Please use a permanent email address, not a disposable one.")
    ok = await domain_accepts_mail(domain)
    if ok is False:
        raise EmailRejected("That email domain can't receive mail. Check the spelling and try again.")
    return email
