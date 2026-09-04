"""
Conversion funnel telemetry. Two halves:

  * record_event: a best-effort writer. It NEVER breaks the caller's request, so
    instrumenting signup can never take signup down.
  * build_funnel: pure and unit-testable. Turns raw events into a step funnel, the
    step-to-step conversion, the single biggest drop-off, and the gate verdict.

The gate metric is visitor -> completed signup. Steps, in order:
  landing_view -> cta_click -> signup_view -> signup_start -> signup_complete
The three top steps are anonymous and counted by DISTINCT anon_id so a refresh does
not inflate a visitor into many. The two signup steps are emitted server-side, one
row per account, and counted by row.

This is the conversion counterpart to services/retention.py, and it stops where that
one starts: conversion covers visitor -> completed signup, retention takes it from
activation onward. No third-party trackers, no PII.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# ── The conversion gate (CGE standard). Change here and in BUILD_STATUS together. ──
CONVERSION_BAR = 0.05          # PASS: >= 5% of visitors complete signup
STOP_LINE = 0.02               # STOP: < 2% -> halt paid traffic, fix the funnel
DEFAULT_WINDOW_DAYS = 30

STEPS = ["landing_view", "cta_click", "signup_view", "signup_start", "signup_complete"]
# Top-of-funnel steps are anonymous; count unique visitors, not raw hits.
_DEDUP_BY_ANON = frozenset({"landing_view", "cta_click", "signup_view"})
# Only these may be written by the public client beacon; the two signup steps are
# server-emitted and must never be spoofable from the browser.
ALLOWED_CLIENT_EVENTS = frozenset({"landing_view", "cta_click", "signup_view"})

# Human labels for the funnel view.
STEP_LABELS = {
    "landing_view": "Visitors",
    "cta_click": "Clicked Start",
    "signup_view": "Reached signup",
    "signup_start": "Created account",
    "signup_complete": "Completed signup",
}


def _get(row: Any, field: str):
    return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


async def record_event(db, event: str, anon_id: Optional[str] = None,
                       organization_id=None, path: Optional[str] = None,
                       meta: Optional[dict] = None) -> None:
    """Best-effort funnel write. Swallows every error so telemetry can never break a
    real flow (signup, onboarding). Commits on its own so it is safe to call after the
    caller has already committed its own work."""
    from backend.models.funnel import FunnelEvent
    try:
        db.add(FunnelEvent(event=event, anon_id=anon_id, organization_id=organization_id,
                           path=path, meta=meta or {}))
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass


def gate_status(rate: Optional[float]) -> str:
    """One of: 'no_data', 'pass', 'watch', 'stop'."""
    if rate is None:
        return "no_data"
    if rate >= CONVERSION_BAR:
        return "pass"
    if rate < STOP_LINE:
        return "stop"
    return "watch"


def _rate(num: int, denom: int) -> Optional[float]:
    if denom <= 0:
        return None
    return round(num / denom, 4)


def build_funnel(rows, now: Optional[datetime] = None,
                 window_days: int = DEFAULT_WINDOW_DAYS) -> Dict[str, Any]:
    """rows: iterable exposing event, anon_id, created_at (one per funnel event).

    Returns per-step counts, step-to-step conversion, the single biggest drop-off
    named with a number, the visitor->completed-signup rate, and the gate verdict.
    """
    now = _naive(now) if now is not None else datetime.utcnow()
    cutoff = now - timedelta(days=window_days)

    # Count each step: unique anon_id for the anonymous steps, raw rows for signup steps.
    seen: Dict[str, set] = {s: set() for s in _DEDUP_BY_ANON}
    raw: Dict[str, int] = {s: 0 for s in STEPS}
    for r in rows:
        ev = _get(r, "event")
        if ev not in raw:
            continue
        ts = _naive(_get(r, "created_at"))
        if ts is not None and ts < cutoff:
            continue
        if ev in _DEDUP_BY_ANON:
            aid = _get(r, "anon_id")
            if aid:
                seen[ev].add(aid)
            else:
                raw[ev] += 1  # anonymous row with no id still counts as one
        else:
            raw[ev] += 1

    counts = {s: (len(seen[s]) + raw[s] if s in _DEDUP_BY_ANON else raw[s]) for s in STEPS}
    steps = [{"step": s, "label": STEP_LABELS[s], "count": counts[s]} for s in STEPS]

    # Step-to-step conversion, and the biggest single leak (most visitors lost).
    conversions: List[Dict[str, Any]] = []
    biggest = None
    for a, b in zip(STEPS, STEPS[1:]):
        prev, cur = counts[a], counts[b]
        lost = max(prev - cur, 0)
        rate = _rate(cur, prev)
        entry = {"from": a, "to": b, "from_label": STEP_LABELS[a], "to_label": STEP_LABELS[b],
                 "rate": rate, "lost": lost}
        conversions.append(entry)
        if prev > 0 and (biggest is None or lost > biggest["lost"]):
            biggest = {**entry, "drop_rate": _rate(lost, prev)}

    visitor_to_signup = _rate(counts["signup_complete"], counts["landing_view"])
    return {
        "window_days": window_days,
        "conversion_bar": CONVERSION_BAR,
        "stop_line": STOP_LINE,
        "steps": steps,
        "step_conversion": conversions,
        "biggest_drop": biggest,
        "visitor_to_signup": visitor_to_signup,
        "gate": gate_status(visitor_to_signup),
    }
