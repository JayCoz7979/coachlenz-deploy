"""Canonical court-zone taxonomy — the single seam between the vision detector's
shot-zone vocabulary and the scouting/report engines.

The detector (worker_ai_detect.py DETECTION_PROMPT_BASKETBALL) emits a richer,
more natural zone vocabulary than the charter's 10 canonical zones. Without a
translation layer the scorer silently miscounts:
  - "Left Wing 3" / "Right Wing 3" / "Top of Key 3" were NOT recognized as threes
    -> a team that shoots wing threes read as "0% threes, wall off the paint."
  - "Free Throw Line" free throws were counted as field-goal attempts -> polluted
    FG% / eFG%.
  - the consistency gate flagged every unmapped label as an "Unknown shot zone."

This module maps every detector label to the canonical taxonomy, tells three from
two by zone, and separates free throws (which are NOT field-goal attempts).
"""
from typing import Optional

# The ten canonical court zones (charter taxonomy). Kept identical to
# basketball_scout.COURT_ZONES so canonical input round-trips unchanged.
CANONICAL_ZONES = [
    "Restricted Area", "Paint Non-RA",
    "Mid-Range Left", "Mid-Range Right", "Mid-Range Center",
    "Left Corner 3", "Right Corner 3",
    "Above-the-Break 3 Left", "Above-the-Break 3 Right", "Above-the-Break 3 Center",
]
THREE_CANONICAL = {
    "Left Corner 3", "Right Corner 3",
    "Above-the-Break 3 Left", "Above-the-Break 3 Right", "Above-the-Break 3 Center",
}
PAINT_CANONICAL = {"Restricted Area", "Paint Non-RA"}
MID_CANONICAL = {"Mid-Range Left", "Mid-Range Right", "Mid-Range Center"}

# The free-throw "zone" the detector emits. A free throw is NOT a field-goal
# attempt, so it never maps to a canonical FG zone — it is handled separately.
FREE_THROW_ZONE = "Free Throw Line"

# raw detector label -> canonical charter zone. Canonical labels map to themselves;
# the detector's variants (Wing 3, Elbow Mid, Mid-Range Left, Half Court heave) fold
# into the canonical bucket that scores them correctly.
_ALIASES = {
    # canonical (identity)
    "Restricted Area": "Restricted Area",
    "Paint Non-RA": "Paint Non-RA",
    "Mid-Range Left": "Mid-Range Left",
    "Mid-Range Right": "Mid-Range Right",
    "Mid-Range Center": "Mid-Range Center",
    "Left Corner 3": "Left Corner 3",
    "Right Corner 3": "Right Corner 3",
    "Above-the-Break 3 Left": "Above-the-Break 3 Left",
    "Above-the-Break 3 Right": "Above-the-Break 3 Right",
    "Above-the-Break 3 Center": "Above-the-Break 3 Center",
    # detector three-point variants
    "Left Wing 3": "Above-the-Break 3 Left",
    "Right Wing 3": "Above-the-Break 3 Right",
    "Top of Key 3": "Above-the-Break 3 Center",
    "Half Court": "Above-the-Break 3 Center",  # a heave is still a 3PA
    # detector mid-range variants
    "Left Elbow Mid": "Mid-Range Left",
    "Right Elbow Mid": "Mid-Range Right",
    "Left Mid-Range": "Mid-Range Left",
    "Right Mid-Range": "Mid-Range Right",
    "Center Mid-Range": "Mid-Range Center",
}
# Case/space-insensitive lookup.
_ALIASES_LC = {k.lower(): v for k, v in _ALIASES.items()}

# Every label the pipeline legitimately produces — the consistency gate accepts
# these instead of only the 10 canonical names (free throws included).
KNOWN_RAW_ZONES = set(_ALIASES) | {FREE_THROW_ZONE}
KNOWN_RAW_ZONES_LC = {z.lower() for z in KNOWN_RAW_ZONES}


def is_free_throw_zone(raw: Optional[str]) -> bool:
    return bool(raw) and raw.strip().lower() == FREE_THROW_ZONE.lower()


def normalize_zone(raw: Optional[str]) -> Optional[str]:
    """Map a detector shot_zone to its canonical charter zone.

    Returns None for empty input, a free throw (not a FG zone), or an
    unrecognized label. Recognized canonical labels round-trip unchanged.
    """
    if not raw:
        return None
    key = raw.strip()
    if is_free_throw_zone(key):
        return None
    return _ALIASES_LC.get(key.lower())


def is_known_zone(raw: Optional[str]) -> bool:
    """True if the label is one the pipeline legitimately emits (incl. free throw)."""
    if not raw:
        return True  # absent zone is not a discrepancy
    return raw.strip().lower() in KNOWN_RAW_ZONES_LC


def is_three_zone(raw: Optional[str]) -> bool:
    z = normalize_zone(raw)
    return z in THREE_CANONICAL


def is_paint_zone(raw: Optional[str]) -> bool:
    z = normalize_zone(raw)
    return z in PAINT_CANONICAL


def is_mid_zone(raw: Optional[str]) -> bool:
    z = normalize_zone(raw)
    return z in MID_CANONICAL
