"""
Roster helpers — pure and unit-testable (no DB, no framework).

CSV parsing maps common header spellings to the canonical roster fields and drops
rows without a jersey and a first name. Jersey resolution normalizes and matches a
read jersey against a roster so EAGLE-EYE reads can be tied to a named player.
"""
import csv
import io
from typing import Any, Dict, List, Optional

# Canonical field -> accepted header spellings (lower-cased, stripped).
ROSTER_CSV_ALIASES: Dict[str, List[str]] = {
    "jersey_number": ["jersey_number", "jersey", "number", "no", "#", "num"],
    "first_name": ["first_name", "first", "firstname", "fname", "given"],
    "last_name": ["last_name", "last", "lastname", "lname", "surname", "family"],
    "position": ["position", "pos"],
    "grade_year": ["grade_year", "grade", "year", "class", "grad_year", "gradyear"],
}


def normalize_jersey(value: Any) -> str:
    """A jersey key that survives '07' vs '7' and stray whitespace. Numeric-looking
    values lose leading zeros; anything else is just trimmed."""
    s = str(value if value is not None else "").strip()
    if s.isdigit():
        return str(int(s))
    return s


def _header_map(fieldnames: List[str]) -> Dict[str, str]:
    """Map each canonical field to the actual CSV header present (if any)."""
    present = {(h or "").strip().lower(): h for h in (fieldnames or [])}
    out = {}
    for field, aliases in ROSTER_CSV_ALIASES.items():
        for alias in aliases:
            if alias in present:
                out[field] = present[alias]
                break
    return out


def parse_roster_csv(text: str) -> List[Dict[str, Optional[str]]]:
    """Parse a roster CSV into canonical player dicts. Requires at least a jersey and
    a first name per row; other fields are optional. Rows missing either are skipped."""
    reader = csv.DictReader(io.StringIO(text))
    hmap = _header_map(reader.fieldnames or [])
    if "jersey_number" not in hmap or "first_name" not in hmap:
        raise ValueError("CSV must include a jersey number column and a first name column.")

    players: List[Dict[str, Optional[str]]] = []
    for row in reader:
        def cell(field):
            col = hmap.get(field)
            v = (row.get(col) if col else None)
            v = (v or "").strip()
            return v or None

        jersey = cell("jersey_number")
        first = cell("first_name")
        if not jersey or not first:
            continue  # skip incomplete rows rather than persist junk
        players.append({
            "jersey_number": normalize_jersey(jersey),
            "first_name": first,
            "last_name": cell("last_name"),
            "position": cell("position"),
            "grade_year": cell("grade_year"),
        })
    return players


def resolve_jersey(players, jersey: Any) -> Optional[Any]:
    """Find the roster player whose jersey matches `jersey` (normalized). `players`
    is any iterable of objects/dicts exposing jersey_number. Returns the match or None."""
    key = normalize_jersey(jersey)
    if not key:
        return None
    for p in players:
        pj = p.get("jersey_number") if isinstance(p, dict) else getattr(p, "jersey_number", None)
        if normalize_jersey(pj) == key:
            return p
    return None
