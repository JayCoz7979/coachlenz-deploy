"""Format check for marketing unsubscribe tokens.

The tokens are random, not signed. Every issuer in this codebase makes one of two
shapes:
  * secrets.token_urlsafe(32): 43 characters of URL-safe base64 (users.default in
    models/user.py and marketing_leads in services/waitlist_capture.py).
  * 32 lowercase hex characters: the users backfill in migration 055
    (gen_random_uuid() with the dashes removed).
Anything outside 32 to 64 URL-safe base64 characters cannot be a real token, so
the API can reject it without a lookup. Every token that has a valid shape gets
the same answer whether or not it matches, so tokens can't be enumerated.
"""
import re

UNSUBSCRIBE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def is_valid_unsubscribe_token(token) -> bool:
    return isinstance(token, str) and bool(UNSUBSCRIBE_TOKEN_RE.fullmatch(token))
