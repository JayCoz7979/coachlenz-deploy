"""Shared slowapi limiter instance.

Lives in its own module so both main.py (which registers it on the app + error
handler) and the routers (which decorate individual endpoints) import the SAME
Limiter. Keyed by client IP.

get_remote_address reads request.client.host, which is the REAL caller only
because uvicorn runs with --proxy-headers --forwarded-allow-ips (see
backend/Dockerfile / railway.toml) and rewrites it from Railway's
X-Forwarded-For. We deliberately do NOT parse X-Forwarded-For ourselves here: a
hand-rolled key_func that trusts the raw header is spoofable (an attacker rotating
the header would mint unlimited buckets and bypass every limit). Trusting the
platform proxy to set it is the safe path.

Storage: with multiple uvicorn workers, slowapi's DEFAULT in-memory storage is
per-process, so each worker counts independently and the effective limit is ~Nx.
Set settings.REDIS_URL to a shared Redis so all workers share ONE counter.
"""
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import settings

logger = logging.getLogger(__name__)


def _build_limiter(storage_uri: str | None) -> Limiter:
    """Build the shared limiter.

    With a redis:// storage_uri every worker shares one counter, so the configured
    per-IP limits are enforced globally instead of per-worker. `in_memory_fallback`
    keeps the API serving on a transient Redis error at request time (degrade to
    local counting rather than 500 every call). Construction itself is also wrapped:
    if Redis is misconfigured/unreachable/its driver is missing at boot, fall back
    to in-memory so a storage problem can never stop the app from starting.
    """
    if storage_uri:
        try:
            lim = Limiter(
                key_func=get_remote_address,
                storage_uri=storage_uri,
                in_memory_fallback_enabled=True,
            )
            logger.info("[ratelimit] using shared Redis storage for rate limits")
            return lim
        except Exception as e:  # unreachable Redis / bad URI / missing driver
            logger.warning(
                "[ratelimit] Redis storage unavailable (%s); falling back to "
                "in-memory (per-worker) limits", e,
            )
    return Limiter(key_func=get_remote_address)


limiter = _build_limiter(settings.REDIS_URL or None)
