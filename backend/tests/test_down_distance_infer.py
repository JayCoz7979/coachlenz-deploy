"""
Down-and-distance carry-forward inference (§12 Map 4 support).
"""
from types import SimpleNamespace

from backend.services.down_distance import infer_down_distance, _advance


def _p(down=None, distance=None, result="Gain", yards=None):
    return SimpleNamespace(down=down, distance=distance, result=result, yards_gained=yards)


# ── chain advancement ────────────────────────────────────────────────────────
def test_advance_normal():
    assert _advance(1, 10, 4, "Gain") == (2, 6)
    assert _advance(2, 6, 3, "Gain") == (3, 3)


def test_advance_first_down_resets():
    assert _advance(3, 3, 5, "Gain") == (1, 10)     # gained enough -> fresh set
    assert _advance(2, 6, 6, "First Down") == (1, 10)


def test_advance_incomplete_keeps_chain():
    assert _advance(1, 10, None, "Incomplete") == (2, 10)   # no gain, same distance


def test_advance_fourth_down_stop_breaks():
    assert _advance(4, 5, 2, "Gain") is None        # 4th & 5, gained 2 -> turnover on downs


def test_advance_breakers_return_none():
    for r in ("Touchdown", "Interception", "Fumble", "Punt", "Penalty", "Field Goal"):
        assert _advance(1, 10, 5, r) is None
    assert _advance(1, 10, None, "Gain") is None     # no yardage, can't advance


# ── sequence filling ─────────────────────────────────────────────────────────
def test_fills_gap_between_anchor_and_breaker():
    plays = [
        _p(1, 10, "Gain", 4),      # anchor -> next 2nd&6
        _p(None, None, "Gain", 3), # fill 2nd&6 -> next 3rd&3
        _p(None, None, "Gain", 5), # fill 3rd&3 (gain 5 -> first down) -> next 1st&10
        _p(None, None, "Gain", 2), # fill 1st&10 -> next 2nd&8
        _p(None, None, "Punt"),    # fill 2nd&8 -> breaker
        _p(None, None, "Gain", 1), # no anchor after breaker -> NOT filled
        _p(3, 7, "Gain", 1),       # anchor (already read)
    ]
    n = infer_down_distance(plays)
    assert n == 4
    assert (plays[1].down, plays[1].distance) == (2, 6) and plays[1].down_distance_inferred is True
    assert (plays[2].down, plays[2].distance) == (3, 3)
    assert (plays[3].down, plays[3].distance) == (1, 10)
    assert (plays[4].down, plays[4].distance) == (2, 8)
    assert plays[5].down is None and plays[5].distance is None      # after breaker, no fill
    assert not hasattr(plays[5], "down_distance_inferred")
    assert not hasattr(plays[0], "down_distance_inferred")          # anchors untouched
    assert not hasattr(plays[6], "down_distance_inferred")


def test_no_fill_before_first_anchor():
    plays = [_p(None, None, "Gain", 3), _p(None, None, "Gain", 2), _p(1, 10, "Gain", 4)]
    n = infer_down_distance(plays)
    assert n == 0
    assert plays[0].down is None and plays[1].down is None


def test_read_anchor_overrides_inference():
    # After 1st&10 gain 4, the chain expects 2nd&6; but the next play READS 1st&10
    # (a new series started) -> the read wins, inference yields.
    plays = [_p(1, 10, "Gain", 4), _p(1, 10, "Gain", 7)]
    infer_down_distance(plays)
    assert (plays[1].down, plays[1].distance) == (1, 10)
    assert not hasattr(plays[1], "down_distance_inferred")


def test_partial_read_neither_anchors_nor_fills():
    # A play with down but no distance (or vice versa) is not trusted to advance,
    # and is not itself filled — it breaks the chain conservatively.
    plays = [_p(1, 10, "Gain", 4), _p(2, None, "Gain", 3), _p(None, None, "Gain", 2)]
    n = infer_down_distance(plays)
    # play[1] is a partial read (down only) -> not filled, breaks chain.
    assert n == 0
    assert plays[2].down is None       # chain broke at the partial read, no state to fill from
