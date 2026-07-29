"""
Usage aggregation / limit helpers — pure and unit-testable (no DB, no framework).
"""
import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional


def month_start(now: datetime) -> datetime:
    """First moment of `now`'s calendar month — the window per-coach caps count over."""
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def over_limit(used: int, limit: Optional[int]) -> bool:
    """True when a coach has hit their monthly cap. limit None or <= 0 = unlimited."""
    if limit is None or limit <= 0:
        return False
    return used >= limit


def _get(row: Any, field: str):
    return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


def aggregate_usage(rows) -> Dict[str, Any]:
    """Roll usage rows up by coach, sport, and analysis type. `rows` is any iterable
    of objects/dicts exposing user_id, sport, analysis_type."""
    by_coach: Dict[str, int] = {}
    by_sport: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    total = 0
    for r in rows:
        total += 1
        uid = str(_get(r, "user_id") or "unknown")
        by_coach[uid] = by_coach.get(uid, 0) + 1
        sport = _get(r, "sport") or "unknown"
        by_sport[sport] = by_sport.get(sport, 0) + 1
        atype = _get(r, "analysis_type") or "unknown"
        by_type[atype] = by_type.get(atype, 0) + 1
    return {"total": total, "by_coach": by_coach, "by_sport": by_sport, "by_type": by_type}


USAGE_CSV_COLUMNS = ["coach", "email", "sport", "analysis_type", "timestamp"]


def usage_to_csv(rows) -> str:
    """One row per run. Each row is a dict/obj with coach, email, sport,
    analysis_type, timestamp (already resolved names — no DB here)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(USAGE_CSV_COLUMNS)
    for r in rows:
        ts = _get(r, "timestamp")
        w.writerow([
            _get(r, "coach") or "",
            _get(r, "email") or "",
            _get(r, "sport") or "",
            _get(r, "analysis_type") or "",
            ts.isoformat() if hasattr(ts, "isoformat") else (ts or ""),
        ])
    return buf.getvalue()
