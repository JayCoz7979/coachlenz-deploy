"""
Retention telemetry. The two numbers that gate the whole product, per cohort.

Pure and unit-testable (no DB, no framework). The admin endpoint feeds ORM rows in;
everything here is plain arithmetic over (organization, analysis) records.

Definitions (a live signup cohort must clear the RETURN bar before any feature
breadth is built, see BUILD_STATUS.md):

  * COHORT: the ISO week an organization signed up (organizations.created_at).
  * ACTION metric  (activation): share of a cohort that completed at least one
    film analysis within ACTIVATION_WINDOW_DAYS of signup. Proof the core action
    was taken at all.
  * RETURN metric  (habit): share of a cohort that ran a SECOND film analysis,
    the second one landing within RETURN_WINDOW_DAYS of signup. Proof coaches
    come back for the core value moment. This is the gated number.

A "film analysis" is one surviving analysis_usage row. The detection worker DELETES
that row when a run fails or dead-letters, so a surviving row is a delivered
analysis, not merely an attempt. That makes analysis_usage the honest core-action
signal and lets retention be DERIVED from real events, with no duplicate write path
that could drift or be faked.

Retention instrumentation is deliberately kept separate from the business usage
dashboard (routers/ad.py): the same events, a different question. This answers
"does the core retain?", never "who used how much?".

A cohort whose RETURN_WINDOW has not fully closed for every member is reported as
still MATURING and never trips the stop line, so an in-window cohort can never
falsely fail the gate.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# ── The retention gate (CGE standard). Change here and in BUILD_STATUS together. ──
RETURN_BAR = 0.40             # PASS: >= 40% of a cohort runs a 2nd analysis in 30d
STOP_LINE = 0.20             # STOP: < 20% return -> halt breadth, fix the core
RETURN_WINDOW_DAYS = 30       # window the 2nd analysis must land within
ACTIVATION_WINDOW_DAYS = 7    # window the 1st analysis must land within
RETURN_MIN_ANALYSES = 2       # a "return" is the second delivered analysis


def _get(row: Any, field: str):
    return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Strip tzinfo so aware DB timestamps compare cleanly against a naive utcnow().
    Mirrors the codebase's to_naive_utc convention used elsewhere."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def iso_cohort(dt: datetime) -> str:
    """Signup week as an ISO-week key, e.g. '2026-W36'. Sorts chronologically."""
    y, w, _ = _naive(dt).isocalendar()
    return f"{y}-W{w:02d}"


def gate_status(return_rate: Optional[float], matured: bool) -> str:
    """One of: 'maturing' (window still open), 'pass', 'watch', or 'stop'."""
    if not matured or return_rate is None:
        return "maturing"
    if return_rate >= RETURN_BAR:
        return "pass"
    if return_rate < STOP_LINE:
        return "stop"
    return "watch"


def _rate(num: int, denom: int) -> Optional[float]:
    if denom <= 0:
        return None
    return round(num / denom, 4)


def build_cohorts(orgs, analyses, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute per-cohort activation + return from organization and analysis rows.

    orgs:     iterable exposing id, created_at.
    analyses: iterable exposing organization_id, created_at (one per delivered run).
    now:      evaluation instant (naive UTC); defaults to datetime.utcnow().

    Returns {'cohorts': [...newest first...], 'summary': {...}} where summary rolls
    up only MATURED cohorts and carries the gate verdict + the configured bar/stop.
    """
    now = _naive(now) if now is not None else datetime.utcnow()

    # Delivered analyses per org, so we can find the 1st and 2nd by time.
    by_org: Dict[str, List[datetime]] = {}
    for a in analyses:
        oid = _get(a, "organization_id")
        ts = _naive(_get(a, "created_at"))
        if oid is None or ts is None:
            continue
        by_org.setdefault(str(oid), []).append(ts)
    for ts_list in by_org.values():
        ts_list.sort()

    # Bucket orgs into cohorts and evaluate each org's activation / return.
    buckets: Dict[str, Dict[str, Any]] = {}
    for o in orgs:
        signup = _naive(_get(o, "created_at"))
        if signup is None:
            continue
        key = iso_cohort(signup)
        b = buckets.setdefault(key, {
            "cohort": key, "size": 0, "activated": 0, "returned": 0,
            "first_signup": signup, "last_signup": signup,
        })
        b["size"] += 1
        b["first_signup"] = min(b["first_signup"], signup)
        b["last_signup"] = max(b["last_signup"], signup)

        runs = by_org.get(str(_get(o, "id")), [])
        if runs and runs[0] <= signup + timedelta(days=ACTIVATION_WINDOW_DAYS):
            b["activated"] += 1
        if len(runs) >= RETURN_MIN_ANALYSES and \
                runs[RETURN_MIN_ANALYSES - 1] <= signup + timedelta(days=RETURN_WINDOW_DAYS):
            b["returned"] += 1

    cohorts: List[Dict[str, Any]] = []
    for b in buckets.values():
        # Matured only once every member's full return window has closed.
        matured = now >= b["last_signup"] + timedelta(days=RETURN_WINDOW_DAYS)
        return_rate = _rate(b["returned"], b["size"])
        cohorts.append({
            "cohort": b["cohort"],
            "size": b["size"],
            "activated": b["activated"],
            "returned": b["returned"],
            "activation_rate": _rate(b["activated"], b["size"]),
            "return_rate": return_rate,
            "matured": matured,
            "gate": gate_status(return_rate, matured),
            "first_signup": b["first_signup"].isoformat(),
            "last_signup": b["last_signup"].isoformat(),
        })
    cohorts.sort(key=lambda c: c["cohort"], reverse=True)

    # Summary rolls up matured cohorts only, the numbers the gate is judged on.
    m_size = sum(c["size"] for c in cohorts if c["matured"])
    m_activated = sum(c["activated"] for c in cohorts if c["matured"])
    m_returned = sum(c["returned"] for c in cohorts if c["matured"])
    overall_return = _rate(m_returned, m_size)
    summary = {
        "return_bar": RETURN_BAR,
        "stop_line": STOP_LINE,
        "return_window_days": RETURN_WINDOW_DAYS,
        "activation_window_days": ACTIVATION_WINDOW_DAYS,
        "matured_cohorts": sum(1 for c in cohorts if c["matured"]),
        "matured_orgs": m_size,
        "activation_rate": _rate(m_activated, m_size),
        "return_rate": overall_return,
        "gate": gate_status(overall_return, m_size > 0),
    }
    return {"cohorts": cohorts, "summary": summary}
