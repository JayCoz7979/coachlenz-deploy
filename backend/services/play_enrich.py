"""
Situational enrichment of AI-detected plays from a coach-supplied CSV.

Single-camera film with no scoreboard overlay leaves down/distance/spot null even
at 1080p — the data isn't in the frames. This lets a coach add that situational
context to the EXISTING detected plays (matched by a stable key) WITHOUT creating
or deleting plays, so the AI's formation/personnel/concept/jersey reads survive and
only the missing situational columns are filled.

Flow: GET a template CSV of the game's plays (each row carries its event_id +
identifying context and blank enrichment columns) -> coach fills DOWN/DISTANCE (and
optionally field position / hash) from the film -> POST it back here.

This module is pure (no DB, no FastAPI): the router loads plays, calls build_
template_csv / parse_enrichment_csv, and applies the parsed updates to events.
"""
import csv
import io
from typing import Optional, List, Dict, Any, Tuple

# The ONLY columns a coach may set here: situational context a scoreboard would
# provide. Detection labels (formation, personnel, play_type, concept...) are NOT
# enrichable — correcting those is the learning-loop's job (PATCH /events), not a
# bulk overwrite, so the AI's reads can never be silently clobbered by a CSV.
ENRICHABLE_FIELDS = ("down", "distance", "field_position", "hash_position")

# Columns the template emits for context so the coach can identify each play on film.
_CONTEXT_COLUMNS = ("side", "formation", "personnel", "play_type", "yards_gained")

_HASH_ALIASES = {
    "l": "left", "left": "left",
    "m": "middle", "mid": "middle", "middle": "middle", "c": "middle", "center": "middle",
    "r": "right", "right": "right",
}

# Header -> canonical field (case/space/punctuation-insensitive).
_HEADER_ALIASES: Dict[str, List[str]] = {
    "event_id": ["eventid", "id"],
    "play_index": ["playindex", "playnumber", "playno", "play", "no", "num", "#", "index"],
    "down": ["down", "dn", "dwn"],
    "distance": ["distance", "dist", "togo", "dst", "togo"],
    "field_position": ["fieldposition", "yardline", "yardln", "yrdln", "spot", "los", "ballon"],
    "hash_position": ["hash", "hashmark", "hashposition"],
}


def _mmss(t: Optional[float]) -> str:
    if t is None:
        return ""
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}"


def _norm(h: str) -> str:
    return "".join(ch for ch in (h or "").lower() if ch.isalnum())


def build_template_csv(plays: List[Dict[str, Any]]) -> str:
    """plays: ordered list of dicts with event_id, time_seconds and current values.
    Returns CSV text: event_id + play_index + context columns + current/blank
    enrichable columns."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["event_id", "play_index", "timestamp", *(_CONTEXT_COLUMNS), *ENRICHABLE_FIELDS])
    for i, p in enumerate(plays, 1):
        w.writerow([
            str(p.get("event_id", "")),
            i,
            _mmss(p.get("time_seconds")),
            *[(p.get(c) if p.get(c) is not None else "") for c in _CONTEXT_COLUMNS],
            *[(p.get(f) if p.get(f) is not None else "") for f in ENRICHABLE_FIELDS],
        ])
    return out.getvalue()


def _coerce(field: str, raw: str) -> Tuple[Any, Optional[str]]:
    """Return (value, error). Blank -> (None, None) meaning 'leave as-is'."""
    v = (raw or "").strip()
    if v == "":
        return None, None
    if field == "down":
        try:
            n = int(float(v))
        except ValueError:
            return None, f"down '{v}' is not a number"
        if not 1 <= n <= 4:
            return None, f"down {n} out of range (1-4)"
        return n, None
    if field == "distance":
        try:
            n = int(float(v))
        except ValueError:
            return None, f"distance '{v}' is not a number"
        if not 0 <= n <= 99:
            return None, f"distance {n} out of range (0-99)"
        return n, None
    if field == "hash_position":
        h = _HASH_ALIASES.get(v.lower())
        if not h:
            return None, f"hash '{v}' not one of left/middle/right"
        return h, None
    if field == "field_position":
        return v[:32], None
    return None, f"unknown field {field}"


def _build_colmap(headers: List[str]) -> Dict[str, str]:
    norm_to_actual = {_norm(h): h for h in headers}
    resolved: Dict[str, str] = {}
    for field, aliases in _HEADER_ALIASES.items():
        if _norm(field) in norm_to_actual:
            resolved[field] = norm_to_actual[_norm(field)]
            continue
        for alias in aliases:
            if _norm(alias) in norm_to_actual:
                resolved[field] = norm_to_actual[_norm(alias)]
                break
    return resolved


def parse_enrichment_csv(csv_text: str) -> Dict[str, Any]:
    """Parse + validate a filled template. Pure — no matching to real events here.

    Returns:
      {
        "header_error": str | None,          # fatal: unusable CSV
        "colmap": {field: header},           # which columns were recognized
        "rows": [ {                          # one per non-blank data row
            "line": int,                     # 1-based data row (for error messages)
            "key_type": "event_id"|"play_index"|None,
            "key": str|int|None,
            "fields": {field: value},        # only the fields the coach filled
            "errors": [str],                 # cell-level problems on this row
        } ],
      }
    """
    reader = csv.reader(io.StringIO(csv_text))
    try:
        headers = next(reader)
    except StopIteration:
        return {"header_error": "CSV is empty", "colmap": {}, "rows": []}

    colmap = _build_colmap(headers)
    have_key = "event_id" in colmap or "play_index" in colmap
    have_any_field = any(f in colmap for f in ENRICHABLE_FIELDS)
    if not have_key:
        return {"header_error": "CSV needs an 'event_id' or 'play_index' column to match plays",
                "colmap": colmap, "rows": []}
    if not have_any_field:
        return {"header_error": f"CSV has none of the enrichable columns: {', '.join(ENRICHABLE_FIELDS)}",
                "colmap": colmap, "rows": []}

    idx = {h: i for i, h in enumerate(headers)}

    def cell(row, field):
        h = colmap.get(field)
        if h is None:
            return ""
        i = idx[h]
        return row[i].strip() if i < len(row) else ""

    rows: List[Dict[str, Any]] = []
    for line_no, row in enumerate(reader, 1):
        if not any((c or "").strip() for c in row):
            continue  # wholly blank line
        errors: List[str] = []
        fields: Dict[str, Any] = {}
        for field in ENRICHABLE_FIELDS:
            val, err = _coerce(field, cell(row, field))
            if err:
                errors.append(err)
            elif val is not None:
                fields[field] = val

        key_type = key = None
        eid = cell(row, "event_id")
        if eid:
            key_type, key = "event_id", eid
        else:
            pidx = cell(row, "play_index")
            if pidx:
                try:
                    key_type, key = "play_index", int(float(pidx))
                except ValueError:
                    errors.append(f"play_index '{pidx}' is not a number")

        if not fields and not errors:
            continue  # coach left every enrichable cell blank -> nothing to do
        rows.append({"line": line_no, "key_type": key_type, "key": key,
                     "fields": fields, "errors": errors})

    return {"header_error": None, "colmap": colmap, "rows": rows}
