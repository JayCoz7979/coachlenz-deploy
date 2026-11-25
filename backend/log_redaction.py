"""Keep signed URL query strings out of the backend logs.

uvicorn's access log prints the full request path, including the query. Local
chunk uploads use /files/multipart/<id>/<n>?sig=<token>, and that token is
valid for hours. This filter rewrites the query of any logged path whose
query carries a signature or token, so the line keeps the path and status but
not the secret. It never drops a log line.
"""
import logging
import re
from urllib.parse import parse_qsl

SENSITIVE_KEYS = frozenset({
    "sig", "signature", "token", "upload_token", "access_token",
    "x-amz-signature", "x-amz-credential", "x-amz-security-token",
})
_URL_QUERY = re.compile(r"(?P<path>/[^\s?\"']*)\?(?P<query>[^\s\"']+)")
REDACTED = "[redacted]"


def _sensitive(query: str) -> bool:
    try:
        keys = {k.lower() for k, _ in parse_qsl(query, keep_blank_values=True)}
    except ValueError:
        return True
    return bool(keys & SENSITIVE_KEYS)


def redact_text(text):
    """Replace the query of every path-with-query in text that holds a secret."""
    if not isinstance(text, str) or "?" not in text:
        return text

    def _sub(match):
        if _sensitive(match.group("query")):
            return f"{match.group('path')}?{REDACTED}"
        return match.group(0)

    return _URL_QUERY.sub(_sub, text)


class RedactSignedQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(redact_text(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact_text(v) for k, v in record.args.items()}
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        return True


def install(logger_names=("uvicorn.access", "uvicorn.error")) -> None:
    """Idempotent. Adds the filter once to each named logger."""
    for name in logger_names:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSignedQueryFilter) for f in logger.filters):
            logger.addFilter(RedactSignedQueryFilter())
