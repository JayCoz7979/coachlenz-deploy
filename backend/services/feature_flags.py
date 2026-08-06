"""Runtime feature-flag control plane.

A platform admin toggles features from the admin panel; the value is stored in the
feature_flags table and read at request time, so a change takes effect WITHOUT a
redeploy. Each flag has an env-var default (the value shipped in Railway); a DB row
overrides it. Absence of a row = use the env default.

Adding a new toggle is two steps: (1) add an entry to FLAGS here, naming the
settings bool that is its default; (2) at the check site, call
`await is_enabled(db, "<key>")` instead of reading settings directly.
"""
import time

from sqlalchemy import select

from backend.config import settings
from backend.models.feature_flag import FeatureFlag

# The togglable features. `env_default` is the Settings attribute used when there's
# no DB override. `category` groups them in the admin UI.
FLAGS: dict[str, dict] = {
    "rerun_confirmation": {
        "label": "Duplicate-run confirmation",
        "description": "Require the coach to confirm — and notify all team coaches — before a 2nd billable analysis on already-analyzed film.",
        "category": "Financial controls",
        "env_default": "RERUN_CONFIRMATION_ENABLED",
    },
    "recruiting_consent": {
        "label": "Recruiting disclosure consent",
        "description": "Require a per-player disclosure attestation before a public recruiting link can be minted.",
        "category": "Compliance",
        "env_default": "RECRUITING_CONSENT_ENABLED",
    },
}

_TTL_SECONDS = 20.0
_cache: dict[str, tuple[bool, float]] = {}  # key -> (value, expires_at monotonic)


def env_default(key: str) -> bool:
    """The shipped default for a flag (its env var), used when no DB override exists."""
    attr = FLAGS.get(key, {}).get("env_default")
    return bool(getattr(settings, attr, False)) if attr else False


async def is_enabled(db, key: str) -> bool:
    """True if the feature is on. DB override wins; otherwise the env default. Cached
    ~20s per worker so it isn't a DB hit on every request (a toggle propagates to all
    workers within the TTL). Never raises — a DB hiccup falls back to the env default."""
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[1] > now:
        return cached[0]
    value: bool | None = None
    try:
        res = await db.execute(select(FeatureFlag.enabled).where(FeatureFlag.key == key))
        value = res.scalar_one_or_none()
    except Exception:
        value = None
    if value is None:
        value = env_default(key)
    _cache[key] = (value, now + _TTL_SECONDS)
    return value


async def list_flags(db) -> list[dict]:
    """Every registered flag with its current effective state, for the admin panel."""
    res = await db.execute(select(FeatureFlag))
    overrides = {f.key: f for f in res.scalars().all()}
    out = []
    for key, meta in FLAGS.items():
        o = overrides.get(key)
        out.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "category": meta["category"],
            "enabled": bool(o.enabled) if o is not None else env_default(key),
            "source": "override" if o is not None else "default",
            "env_default": env_default(key),
        })
    return out


async def set_flag(db, key: str, enabled: bool, user_id) -> None:
    """Upsert an override for `key`. Invalidates this worker's cache immediately;
    other workers refresh within the TTL."""
    if key not in FLAGS:
        raise ValueError(f"unknown feature flag: {key}")
    existing = (await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
    if existing is None:
        db.add(FeatureFlag(key=key, enabled=enabled, updated_by=user_id))
    else:
        existing.enabled = enabled
        existing.updated_by = user_id
    await db.commit()
    _cache.pop(key, None)


def _clear_cache() -> None:
    """Test hook: drop the per-worker cache."""
    _cache.clear()
