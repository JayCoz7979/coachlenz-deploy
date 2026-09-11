"""
Basketball possession anchor (the fix for offense/defense flipping).

A 20-year film analyst does not re-read the ball-handler's jersey every possession —
on a wide single-cam angle you cannot. They anchor to DIRECTION: each team attacks one
basket for a whole half, flipping only at halftime, so possession is decided by which
basket the ball is heading toward (big and obvious on film even when jerseys are tiny).

This turns the model's per-play `attack_direction` (which basket the offense attacks,
"left"/"right" on screen) into a consistent per-half offense/defense assignment:

  - If the coach set the scouted team's first-half attacking direction, possession is
    DETERMINISTIC: offense = attacking that basket in H1 and the opposite basket in H2.
    It cannot drift, because it is not guessing per possession.
  - If not set, it AUTO-anchors: within each half, the direction that most co-occurs
    with the model's offense reads becomes "offense direction", and every play in that
    half is made consistent with it (H2 is the opposite). Even if a whole half is
    inverted, it is CONSISTENT, so a coach flips it once instead of fixing every play.

Pure and deterministic (no model call, no DB) so it is fully unit-testable.
"""
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

_OPP = {"left": "right", "right": "left"}
# Sides the anchor may correct. Never touches a timeout, and leaves 'transition'
# (a fast break, which is still that team's offense) as the model read.
_CORRECTABLE = {"offense", "defense"}


def _norm_dir(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    if "left" in s:
        return "left"
    if "right" in s:
        return "right"
    return None


def _half_of(quarter: Any) -> Optional[int]:
    """1 for Q1-2, 2 for Q3-4 and overtime (teams keep the 2nd-half baskets in OT).
    None when the quarter is unknown."""
    try:
        q = int(quarter)
    except (TypeError, ValueError):
        return None
    if q in (1, 2):
        return 1
    if q >= 3:
        return 2
    return None


def anchor_sides(plays: List[Dict[str, Any]],
                 scout_attack_dir_h1: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Make every play's side consistent with the direction of attack, per half.
    Mutates `side` in place and returns (plays, changed_count)."""
    if not plays:
        return plays, 0

    coach = _norm_dir(scout_attack_dir_h1)
    offense_dir: Dict[Optional[int], str] = {}

    if coach:
        offense_dir = {1: coach, 2: _OPP[coach], None: coach}
    else:
        # Auto: per half, the direction most correlated with the model's offense reads.
        for h in (1, 2, None):
            c: Counter = Counter()
            for p in plays:
                if _half_of(p.get("quarter")) != h:
                    continue
                d = _norm_dir(p.get("attack_direction"))
                if d and p.get("side") == "offense":
                    c[d] += 1
            if c:
                offense_dir[h] = c.most_common(1)[0][0]
        # If only one half was resolvable, the other half is simply the opposite.
        if 1 in offense_dir and 2 not in offense_dir:
            offense_dir[2] = _OPP[offense_dir[1]]
        if 2 in offense_dir and 1 not in offense_dir:
            offense_dir[1] = _OPP[offense_dir[2]]
        # Unknown-quarter plays fall back to the H1 mapping.
        if None not in offense_dir and 1 in offense_dir:
            offense_dir[None] = offense_dir[1]

    changed = 0
    for p in plays:
        d = _norm_dir(p.get("attack_direction"))
        if not d:
            continue
        od = offense_dir.get(_half_of(p.get("quarter")))
        if od is None:
            od = offense_dir.get(None)
        if od is None:
            continue
        if (p.get("side") or "") not in _CORRECTABLE:
            continue
        new_side = "offense" if d == od else "defense"
        if p.get("side") != new_side:
            p["side"] = new_side
            p["side_source"] = "direction_anchor"
            changed += 1
    return plays, changed
