"""
Coach-flagged plays for the report — pure and unit-testable (no DB, no framework).

The film-room lets a coach star plays (is_highlight) and write a note (coach_note)
on any play. This turns those flagged plays into a compact, chronological digest the
report writer folds into the prompt, so the coach's own reads land in the generated
report verbatim rather than being lost the moment analysis aggregates the plays.
"""
from typing import Any, Iterable, List

# Bound the prompt: a report should surface the coach's key plays, not a 300-row
# dump. If a coach flags more than this, keep the earliest and note the trim.
FLAGGED_LIMIT = 60


def _clock(secs) -> str:
    if secs is None:
        return "--"
    try:
        s = int(secs)
    except (TypeError, ValueError):
        return "--"
    return f"{s // 60}:{s % 60:02d}"


def _play_tag(e: Any) -> str:
    """A short, sport-agnostic descriptor of a play from whatever fields it carries."""
    x = getattr(e, "extra_data", None) or {}
    parts: List[str] = []

    et = getattr(e, "event_type", None)
    if et and et != "play":
        parts.append(str(et).replace("_", " "))

    down = getattr(e, "down", None)
    if down:
        dist = getattr(e, "distance", None)
        parts.append(f"{down}&{dist}" if dist is not None else str(down))

    for f in (getattr(e, "formation", None), getattr(e, "play_type", None),
              x.get("shot_zone"), getattr(e, "coverage", None), getattr(e, "result", None)):
        if f:
            parts.append(str(f))

    yg = getattr(e, "yards_gained", None)
    if isinstance(yg, (int, float)) and not isinstance(yg, bool):
        parts.append(f"{'+' if yg > 0 else ''}{int(yg)} yds")

    player = getattr(e, "player", None)
    if player:
        parts.append(f"#{player}")

    return " · ".join(parts) or "play"


def collect_flagged_plays(events: Iterable[Any], limit: int = FLAGGED_LIMIT) -> List[dict]:
    """Chronological digest of the plays a coach starred or annotated. Each item:
    {clock, tag, note, is_highlight}. scout_meta rows are skipped. Returns [] when the
    coach flagged nothing (the report then simply omits the coach's-notes section)."""
    flagged = []
    for e in events:
        if getattr(e, "event_type", None) == "scout_meta":
            continue
        note = (getattr(e, "coach_note", None) or "").strip()
        highlight = bool(getattr(e, "is_highlight", False))
        if not note and not highlight:
            continue
        flagged.append({
            "time_seconds": getattr(e, "time_seconds", None),
            "clock": _clock(getattr(e, "time_seconds", None)),
            "tag": _play_tag(e),
            "note": note,
            "is_highlight": highlight,
        })

    # Chronological (untimed plays last), then cap.
    flagged.sort(key=lambda f: (f["time_seconds"] is None, f["time_seconds"] or 0))
    trimmed = flagged[:limit]
    for f in trimmed:
        f.pop("time_seconds", None)
    return trimmed
