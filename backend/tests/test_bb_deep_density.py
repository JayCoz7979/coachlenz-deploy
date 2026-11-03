"""
Regression: DEEP-mode frame-density inversion for non-football sports.

The multipass ANALYSIS path (2-3 vision calls per batch) is implemented only for
football/flag_football. Deep mode trades frame density for that extra reasoning
(FRAMES_PER_WINDOW_DEEP < FRAMES_PER_WINDOW_FAST). The density cut used to key off
"was deep requested" (self._multipass) instead of "does multipass actually run",
so a basketball DEEP run dropped ~24% of its frames (50/window vs 66) for no
compensating depth, hurting recall on the premium path.

_resolve_multipass_active(sport) is now the single source of truth: deep AND a
football sport. These are pure-function tests on it plus the density mapping the
worker derives from it (no ffmpeg, no vision API, no DB, no paid inference).

Run:  python -m backend.tests.test_bb_deep_density
"""
from backend.workers.worker_ai_detect import (
    AiDetectWorker,
    FRAMES_PER_WINDOW_FAST,
    FRAMES_PER_WINDOW_DEEP,
)

w = AiDetectWorker()
passed, failed = 0, 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {label}")
    else:
        failed += 1; print(f"  FAIL  {label}")


def _density(active):
    """Mirror the worker's selection at the frame-extraction call site."""
    return FRAMES_PER_WINDOW_DEEP if active else FRAMES_PER_WINDOW_FAST


def test_deep_basketball_is_not_multipass_active():
    w._multipass = True   # coach picked DEEP
    assert w._resolve_multipass_active("basketball") is False


def test_deep_football_is_multipass_active():
    w._multipass = True
    assert w._resolve_multipass_active("football") is True


def test_deep_flag_football_is_multipass_active():
    w._multipass = True
    assert w._resolve_multipass_active("flag_football") is True


def test_fast_mode_is_never_multipass_active():
    w._multipass = False  # coach picked FAST
    assert w._resolve_multipass_active("football") is False
    assert w._resolve_multipass_active("basketball") is False


def test_missing_multipass_attr_defaults_false():
    if hasattr(w, "_multipass"):
        delattr(w, "_multipass")
    assert w._resolve_multipass_active("football") is False


def test_sport_is_case_insensitive():
    w._multipass = True
    assert w._resolve_multipass_active("BASKETBALL") is False
    assert w._resolve_multipass_active("Football") is True


def test_basketball_deep_keeps_fast_density():
    """The core recall fix: a basketball DEEP run keeps the denser FAST sampling
    instead of the thinner DEEP grid."""
    w._multipass = True
    assert _density(w._resolve_multipass_active("basketball")) == FRAMES_PER_WINDOW_FAST


def test_football_deep_still_uses_deep_density():
    """Football DEEP is unchanged: it still trades density for multipass depth."""
    w._multipass = True
    assert _density(w._resolve_multipass_active("football")) == FRAMES_PER_WINDOW_DEEP


def test_fast_is_denser_than_deep():
    assert FRAMES_PER_WINDOW_FAST > FRAMES_PER_WINDOW_DEEP


_TESTS = [
    test_deep_basketball_is_not_multipass_active,
    test_deep_football_is_multipass_active,
    test_deep_flag_football_is_multipass_active,
    test_fast_mode_is_never_multipass_active,
    test_missing_multipass_attr_defaults_false,
    test_sport_is_case_insensitive,
    test_basketball_deep_keeps_fast_density,
    test_football_deep_still_uses_deep_density,
    test_fast_is_denser_than_deep,
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
