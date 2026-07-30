"""
Inactive-coach detection — pure and unit-testable (no DB, no framework).

A coach's "last activity" is the most recent of two already-tracked signals:
  * last_login_at  — set on every login (auth.py)
  * their most recent analysis run (AnalysisUsage.created_at) — the core work action

A coach is flagged inactive when that timestamp is older than `days` (or when there
is no activity on record at all — a seat that was created and never used). Both
signals are compared in naive-UTC so DB-aware timestamps never blow up against
utcnow() (see utils/timeutils).
"""
from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional

from backend.utils.timeutils import to_naive_utc

DEFAULT_INACTIVE_DAYS = 14
MIN_INACTIVE_DAYS = 1
MAX_INACTIVE_DAYS = 365


def clamp_days(days: Any) -> int:
    try:
        d = int(days)
    except (TypeError, ValueError):
        return DEFAULT_INACTIVE_DAYS
    return max(MIN_INACTIVE_DAYS, min(MAX_INACTIVE_DAYS, d))


def _last_run_by_user(usage_rows: Iterable[Any]) -> dict:
    """Most recent analysis run timestamp per user_id (naive UTC)."""
    latest: dict = {}
    for r in usage_rows:
        uid = str(getattr(r, "user_id", "") or "")
        ts = to_naive_utc(getattr(r, "created_at", None))
        if not uid or ts is None:
            continue
        if uid not in latest or ts > latest[uid]:
            latest[uid] = ts
    return latest


def last_active_at(user: Any, last_run: Optional[datetime]) -> Optional[datetime]:
    """The later of a user's last login and last analysis run (naive UTC), or None
    if neither exists."""
    candidates = [to_naive_utc(getattr(user, "last_login_at", None)), last_run]
    present = [c for c in candidates if c is not None]
    return max(present) if present else None


def compute_inactive_coaches(
    users: Iterable[Any],
    usage_rows: Iterable[Any],
    now: datetime,
    days: int = DEFAULT_INACTIVE_DAYS,
    exclude_user_id: Optional[str] = None,
) -> List[dict]:
    """Return the org's inactive coaches, most-stale first (never-active before
    merely-lapsed). `now` is passed in for testability. `exclude_user_id` drops the
    viewer (an AD needn't see themselves)."""
    days = clamp_days(days)
    cutoff = now - timedelta(days=days)
    runs = _last_run_by_user(usage_rows)
    exclude = str(exclude_user_id) if exclude_user_id else None

    out: List[dict] = []
    for u in users:
        uid = str(getattr(u, "id", "") or "")
        if not uid or uid == exclude:
            continue
        active_at = last_active_at(u, runs.get(uid))
        if active_at is not None and active_at >= cutoff:
            continue  # active within the window
        never = active_at is None
        days_inactive = None if never else (now - active_at).days
        out.append({
            "user_id": uid,
            "name": getattr(u, "name", None),
            "email": getattr(u, "email", None),
            "role": getattr(u, "role", None),
            "last_active_at": (active_at.isoformat() if active_at else None),
            "days_inactive": days_inactive,
            "never_active": never,
        })

    # Never-active first, then longest-inactive first.
    out.sort(key=lambda c: (0 if c["never_active"] else 1, -(c["days_inactive"] or 0)))
    return out
