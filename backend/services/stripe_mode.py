"""Stripe live/test mode guard (Stage 2 QA L2).

Outside production, CoachLenz must only ever talk to Stripe in TEST mode:
  * the app refuses to start with a live secret key (``sk_live_`` / ``rk_live_``),
  * every checkout endpoint that uses this guard refuses (503) with one, and
  * the webhook ignores any event whose ``livemode`` does not match the environment
    (production expects livemode=true, everything else livemode=false).

"Production" means ENVIRONMENT is EXPLICITLY "production". ENVIRONMENT has no default:
config.Settings refuses to load when it is unset or blank, so a service that forgot
to set it never starts (and so can never be mistaken for production with a live key).
"""
from typing import Any, Optional

from backend.config import settings

LIVE_KEY_PREFIXES = ("sk_live_", "rk_live_")


def is_production() -> bool:
    return (settings.ENVIRONMENT or "").strip().lower() == "production"


def live_key_outside_production(key: Optional[str] = None) -> bool:
    k = (settings.STRIPE_SECRET_KEY if key is None else key) or ""
    return (not is_production()) and k.strip().startswith(LIVE_KEY_PREFIXES)


def assert_stripe_mode_safe_at_startup() -> None:
    """Raise (so the app does not start) when a live key is configured outside production.
    The message names the setting, never its value."""
    if live_key_outside_production():
        raise RuntimeError(
            "Refusing to start: STRIPE_SECRET_KEY is a live-mode key but ENVIRONMENT is not "
            "'production'. Use a Stripe test key (sk_test_) outside production."
        )


def expected_livemode() -> bool:
    return is_production()


def event_livemode_mismatch(event: Any) -> bool:
    """True when a signed event's livemode disagrees with this environment.

    Stripe always sends ``livemode``; an event without it (only hand-built test
    fixtures) is not treated as a mismatch."""
    try:
        lm = event.get("livemode")
    except AttributeError:
        lm = getattr(event, "livemode", None)
    if lm is None:
        return False
    return bool(lm) != expected_livemode()
