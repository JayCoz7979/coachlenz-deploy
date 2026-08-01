"""
Down-and-distance carry-forward inference (Engine §12 support).

Scoreboard OCR reads down/distance on only SOME football plays — a wide fixed
camera often can't resolve the score bug. But football's down-and-distance chain
is deterministic: if one play reads "1st & 10" and gains 4, the next play is
"2nd & 6" even when its own scoreboard was unreadable. This fills those gaps
BETWEEN scoreboard-read anchors, conservatively, and resets on any chain-breaker
(score, turnover, punt, penalty, 4th-down stop). Filled plays are marked
`down_distance_inferred = True` so the read stays honest and auditable — this
infers from structure, it does not fabricate.

Pure and deterministic (no model call): operates on a TIME-ORDERED list of one
team's offense plays and mutates them in place. Returns how many it filled.
"""
from typing import Any, List, Optional, Tuple

# Results that end a series or change distance unpredictably. On any of these we
# stop inferring until the next scoreboard-read anchor re-establishes the chain.
_BREAKERS = (
    "touchdown", "interception", "fumble", "turnover", "punt",
    "field goal", "safety", "penalty",
)


def _num(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _advance(down: int, distance: int, yards, result) -> Optional[Tuple[int, int]]:
    """Given a play's down/distance and its outcome, return the NEXT play's
    (down, distance), or None if the chain breaks or can't be advanced."""
    r = (result or "").strip().lower()
    if any(b in r for b in _BREAKERS):
        return None
    y = _num(yards)
    if y is None:
        # An incomplete pass gains nothing but keeps the chain alive; anything else
        # we can't advance without the yardage, so break.
        if "incomplete" in r:
            y = 0
        else:
            return None
    new_dist = distance - y
    if new_dist <= 0:
        return (1, 10)          # first down reached -> fresh set
    if down >= 4:
        return None             # 4th down, no first down -> turnover on downs
    return (down + 1, new_dist)


def infer_down_distance(offense_plays: List[Any]) -> int:
    """Fill missing down/distance on TIME-ORDERED offense plays from the chain.

    Only fills a gap that sits between a read anchor and a breaker; never invents
    the first play of a series, and never overrides a play that already read a
    down/distance. A partial read (one field only) neither anchors nor advances.
    Mutates plays in place (sets down, distance, down_distance_inferred=True on
    filled plays). Returns the count filled.
    """
    filled = 0
    state: Optional[Tuple[int, int]] = None   # expected (down, distance) for THIS play
    for p in offense_plays:
        rd = _num(getattr(p, "down", None))
        rdist = _num(getattr(p, "distance", None))
        if rd is not None and rdist is not None:
            cur: Optional[Tuple[int, int]] = (rd, rdist)      # full read -> trust it (anchor)
        elif rd is None and rdist is None and state is not None:
            p.down, p.distance = state[0], state[1]           # fill the gap from the chain
            setattr(p, "down_distance_inferred", True)
            filled += 1
            cur = state
        else:
            cur = None                                         # partial read / no anchor -> break
        state = _advance(cur[0], cur[1], getattr(p, "yards_gained", None),
                         getattr(p, "result", None)) if cur else None
    return filled
