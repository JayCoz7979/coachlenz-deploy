"""
Regression: sport-aware play dedup window (basketball recall).

Reproduces the basketball miss where the single, sport-blind 8-second dedup
window in _deduplicate_plays merged two DISTINCT basketball plays that happen
within 8s of each other (transition buckets, offensive-rebound putbacks,
steals, back-to-back free throws) into one, silently dropping the second play.

These are pure-function tests on the real _deduplicate_plays method (no ffmpeg,
no vision API, no DB, no paid inference). Synthetic detection lists stand in for
the vision output; the timestamps are the only thing dedup looks at.

Run:  python -m backend.tests.test_bb_dedup_recall
"""
from backend.workers.worker_ai_detect import (
    AiDetectWorker,
    DEDUP_WINDOW_SECONDS,
    DEDUP_WINDOW_SECONDS_BASKETBALL,
)

w = AiDetectWorker()
passed, failed = 0, 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {label}")
    else:
        failed += 1; print(f"  FAIL  {label}")


# ── Core regression: the fixed miss ──────────────────────────────────────────
def test_basketball_keeps_two_distinct_plays_within_8s():
    """Two distinct basketball plays 5s apart must BOTH survive (the old 8s
    window dropped the second)."""
    plays = [
        {"time_seconds": 100.0, "confidence": 0.90},  # made basket
        {"time_seconds": 105.0, "confidence": 0.80},  # transition bucket 5s later
    ]
    out = w._deduplicate_plays(list(plays), sport="basketball")
    assert len(out) == 2, out


def test_football_still_merges_two_plays_within_8s():
    """Same input as basketball, but football KEEPS the 8s window: the two
    within-8s detections collapse to one. Proves the miss is sport-specific and
    the football path is unchanged."""
    plays = [
        {"time_seconds": 100.0, "confidence": 0.90},
        {"time_seconds": 105.0, "confidence": 0.80},
    ]
    out = w._deduplicate_plays(list(plays), sport="football")
    assert len(out) == 1, out


def test_default_sport_is_football_behavior():
    """A caller that does not pass sport must get the historical football
    behavior (8s window) so no existing caller changes silently."""
    plays = [
        {"time_seconds": 100.0, "confidence": 0.90},
        {"time_seconds": 105.0, "confidence": 0.80},
    ]
    assert len(w._deduplicate_plays(list(plays))) == 1


def test_basketball_still_collapses_same_moment_echo():
    """Dedup must still work for basketball: two detections of the SAME event
    1.5s apart (below the basketball window) collapse to one, keeping the more
    confident read. Guards against double-counting adjacent-frame echoes."""
    plays = [
        {"time_seconds": 100.0, "confidence": 0.70},
        {"time_seconds": 101.5, "confidence": 0.90},  # same event, higher conf
    ]
    out = w._deduplicate_plays(list(plays), sport="basketball")
    assert len(out) == 1, out
    assert out[0]["confidence"] == 0.90, out


def test_basketball_back_to_back_free_throws_both_kept():
    """Back-to-back free throws ~4s apart are distinct scoring plays and must
    both survive for basketball."""
    plays = [
        {"time_seconds": 200.0, "confidence": 0.88},
        {"time_seconds": 204.0, "confidence": 0.85},
    ]
    out = w._deduplicate_plays(list(plays), sport="basketball")
    assert len(out) == 2, out


def test_basketball_realistic_sequence_recall_vs_football():
    """A realistic mixed possession burst: five raw detections where three are
    distinct plays (>=3s apart) and two are same-moment echoes (<3s). Basketball
    must keep the three distinct plays; football (8s) collapses the whole burst
    far more aggressively. Shows the net recall difference end of stage."""
    raw = [
        {"time_seconds": 300.0, "confidence": 0.90},  # shot
        {"time_seconds": 301.0, "confidence": 0.60},  # echo of the shot (<3s) -> merge
        {"time_seconds": 304.0, "confidence": 0.85},  # putback 4s later -> distinct
        {"time_seconds": 309.0, "confidence": 0.80},  # transition 5s later -> distinct
        {"time_seconds": 310.0, "confidence": 0.55},  # echo (<3s) -> merge
    ]
    bb = w._deduplicate_plays(list(raw), sport="basketball")
    fb = w._deduplicate_plays(list(raw), sport="football")
    # Basketball keeps the three distinct plays (300 shot, 304 putback, 309
    # transition); the two sub-3s echoes (301, 310) merge into their neighbors.
    assert len(bb) == 3, bb
    # Football's 8s window absorbs 301 and 304 into 300 and 310 into 309, leaving
    # only the two detections that sit 9s apart. Basketball recovers one more play.
    assert len(fb) == 2, fb
    assert len(bb) > len(fb), (bb, fb)


def test_empty_list():
    assert w._deduplicate_plays([], sport="basketball") == []
    assert w._deduplicate_plays([]) == []


def test_window_constants_sane():
    """The basketball window must be materially tighter than football, and tight
    enough that two FAST-sampled plays (4.5s apart) are not merged away."""
    assert DEDUP_WINDOW_SECONDS_BASKETBALL < DEDUP_WINDOW_SECONDS
    assert DEDUP_WINDOW_SECONDS_BASKETBALL < 4.5  # below the FAST frame-sampling gap


_TESTS = [
    test_basketball_keeps_two_distinct_plays_within_8s,
    test_football_still_merges_two_plays_within_8s,
    test_default_sport_is_football_behavior,
    test_basketball_still_collapses_same_moment_echo,
    test_basketball_back_to_back_free_throws_both_kept,
    test_basketball_realistic_sequence_recall_vs_football,
    test_empty_list,
    test_window_constants_sane,
]


def run():
    for t in _TESTS:
        try:
            t()
            check(t.__name__, True)
        except AssertionError as e:
            check(f"{t.__name__}  ->  {e}", False)
    print(f"\n{'='*50}\n  {passed} passed, {failed} failed\n{'='*50}")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
