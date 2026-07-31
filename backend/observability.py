"""
Sentry initialization shared by the API and the worker processes.

The dedicated worker services run as their own processes (`python -m
backend.workers.worker_*`) and never import main.py, so before this they inited
no Sentry — the heaviest, most crash-prone work (film ingest, multi-pass Opus
detection) reported errors to nothing but Railway stdout. init_sentry() is called
from both main.py (component="api") and BaseWorker.run_forever()
(component="worker:<job_type>") so every process is covered.

Both functions are safe no-ops when SENTRY_DSN is unset.
"""
import logging

import sentry_sdk

from backend.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def init_sentry(component: str) -> None:
    """Idempotent Sentry init for any process. No-op without SENTRY_DSN."""
    global _initialized
    if _initialized or not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
    )
    sentry_sdk.set_tag("component", component)
    _initialized = True
    logger.info("[observability] Sentry initialized (%s)", component)


def capture(exc: BaseException, **tags) -> None:
    """Report an exception to Sentry with optional tags. Safe no-op if Sentry is
    not configured; never raises (observability must not break the caller)."""
    if not settings.SENTRY_DSN:
        return
    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in tags.items():
                scope.set_tag(key, value)
            sentry_sdk.capture_exception(exc)
    except Exception:  # pragma: no cover - reporting must never crash the worker
        pass
