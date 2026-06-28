"""Down & distance propagation from coach anchors.

On single-camera / press-box film with no scoreboard, the AI rarely reads down
and distance. But a coach only has to tag a few anchors (e.g. the 1st & 10 that
starts each drive); from there we propagate the chain forward using each play's
yardage: 1st & 10, gain of 4 -> 2nd & 6, gain of 6 -> 1st & 10, and so on.

We only FILL missing values. We never overwrite a value already present (coach or
AI), so existing tags stay authoritative and act as fresh anchors down the drive.
"""
from typing import List, Dict, Any


def _is_offense(side) -> bool:
    return (side or "offense") == "offense"


def fill_down_distance(plays: List[Dict[str, Any]]) -> int:
    """Fill missing down/distance in-place by forward-propagating from anchors.

    `plays` is a time-sorted list of dicts with at least: side, down, distance,
    yards_gained. Returns the number of fields filled.

    State machine, reset on every possession change:
    - A play with both down and distance is an ANCHOR (trusted, used as-is).
    - A play missing them inherits the running state (if we have one).
    - After each play, advance the state using yards_gained:
        new_distance = distance - yards_gained
        <= 0            -> 1st & 10 (first down / series reset)
        down was 4th    -> possession likely changed, stop the chain
        otherwise       -> (down + 1, new_distance)
    - Missing yardage breaks the chain (we won't guess past an unknown gain).
    """
    filled = 0
    state = None  # running (down, distance) expected for the NEXT play

    for p in plays:
        if not _is_offense(p.get("side")):
            state = None  # defense / special teams -> possession boundary
            continue

        has_dd = p.get("down") is not None and p.get("distance") is not None
        if has_dd:
            cur = (p["down"], p["distance"])  # anchor wins
        elif state is not None:
            cur = state
            if p.get("down") is None:
                p["down"] = cur[0]
                p["down_source"] = "derived"
                filled += 1
            if p.get("distance") is None:
                p["distance"] = cur[1]
                p["distance_source"] = "derived"
                filled += 1
        else:
            cur = None

        # Advance the chain for the next play.
        yg = p.get("yards_gained")
        if cur is None or yg is None:
            state = None
            continue
        down, dist = cur
        try:
            new_dist = dist - int(yg)
        except (TypeError, ValueError):
            state = None
            continue
        if new_dist <= 0:
            state = (1, 10)            # converted / series reset
        elif down >= 4:
            state = None               # 4th down not converted -> change of possession
        else:
            state = (down + 1, new_dist)

    return filled
