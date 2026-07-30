"""
Deterministic tests for the basketball detection-artifact scrub
(`AiDetectWorker._sanitize_bb_events`). Single-camera vision over-tags dead
balls as `timeout`; this filter holds timeouts to a confidence floor + a
per-game cap while leaving every other event untouched. Pure function, no
ffmpeg / vision API needed.
"""
import pytest

from backend.workers.worker_ai_detect import (
    AiDetectWorker,
    TIMEOUT_MIN_CONFIDENCE,
    MAX_PLAUSIBLE_TIMEOUTS,
)

w = AiDetectWorker()


def _to(conf):
    return {"event_type": "timeout", "confidence": conf}


def _shot(conf=0.9):
    return {"event_type": "shot", "confidence": conf}


@pytest.mark.unit
def test_no_timeouts_passes_through_unchanged():
    plays = [_shot(), {"event_type": "turnover"}, _shot(0.6)]
    clean, dropped = w._sanitize_bb_events(plays)
    assert dropped == 0
    assert clean == plays  # same objects, same order


@pytest.mark.unit
def test_low_confidence_timeouts_dropped_by_floor():
    below = TIMEOUT_MIN_CONFIDENCE - 0.1
    at = TIMEOUT_MIN_CONFIDENCE
    plays = [_to(below), _to(below), _to(at)]
    clean, dropped = w._sanitize_bb_events(plays)
    kept = [p for p in clean if p["event_type"] == "timeout"]
    assert len(kept) == 1 and kept[0]["confidence"] == at
    assert dropped == 2


@pytest.mark.unit
def test_hard_cap_keeps_highest_confidence():
    # More confident timeouts than the plausible cap allows.
    confs = [0.75 + i * 0.001 for i in range(MAX_PLAUSIBLE_TIMEOUTS + 8)]
    plays = [_to(c) for c in confs]
    clean, dropped = w._sanitize_bb_events(plays)
    kept = [p for p in clean if p["event_type"] == "timeout"]
    assert len(kept) == MAX_PLAUSIBLE_TIMEOUTS
    assert dropped == 8
    # The survivors are exactly the most-confident MAX_PLAUSIBLE_TIMEOUTS reads.
    expected = sorted(confs, reverse=True)[:MAX_PLAUSIBLE_TIMEOUTS]
    assert sorted(p["confidence"] for p in kept) == sorted(expected)


@pytest.mark.unit
def test_non_timeout_events_never_touched_and_order_preserved():
    plays = [_shot(0.9), _to(0.4), {"event_type": "steal", "confidence": 0.5},
             _to(0.99), {"event_type": "block", "confidence": 0.55}]
    clean, dropped = w._sanitize_bb_events(plays)
    # Every non-timeout survives, in original relative order.
    non_to = [p for p in clean if p["event_type"] != "timeout"]
    assert [p["event_type"] for p in non_to] == ["shot", "steal", "block"]
    # The 0.4 timeout is dropped (below floor); the 0.99 survives.
    kept_to = [p for p in clean if p["event_type"] == "timeout"]
    assert len(kept_to) == 1 and kept_to[0]["confidence"] == 0.99
    assert dropped == 1


@pytest.mark.unit
def test_thirty_four_timeouts_scrubbed_to_plausible():
    # The real single-cam failure: 34 timeout events, mixed confidence.
    plays = [_shot() for _ in range(20)]
    plays += [_to(0.5) for _ in range(20)]   # dead-ball guesses, below floor
    plays += [_to(0.85) for _ in range(14)]  # confident-looking, still implausible count
    clean, dropped = w._sanitize_bb_events(plays)
    kept_to = [p for p in clean if p["event_type"] == "timeout"]
    assert len(kept_to) <= MAX_PLAUSIBLE_TIMEOUTS
    # All 20 shots survive untouched.
    assert len([p for p in clean if p["event_type"] == "shot"]) == 20
    assert dropped == 34 - len(kept_to)
