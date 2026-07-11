"""Datetime normalization helpers.

The recurring bug: our Postgres columns are DateTime(timezone=True), so they read
back timezone-AWARE, but application code compares them against a naive
datetime.utcnow(). Mixing aware and naive datetimes raises
`TypeError: can't compare offset-naive and offset-aware datetimes`, which has 500'd
live endpoints more than once (detect status, and nearly the email-verify cooldown).

Rule: run any datetime that came from the database through `to_naive_utc()` before
comparing it to `utcnow()`. Don't hand-roll `.replace(tzinfo=None)` at each call site.
"""
from datetime import datetime, timezone
from typing import Optional


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Return `dt` as a naive UTC datetime (tzinfo stripped), or None.

    Aware values are converted to UTC first, so the wall-clock is correct even if
    the source tz wasn't UTC. Naive values pass through unchanged (assumed UTC,
    which is how utcnow() writes them)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
