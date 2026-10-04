"""Fast-path made/miss verify: the shaky-shot selector picks only uncertain shots,
prioritizes paint/rim (where single-cam misreads makes as misses), and respects the cap."""
from backend.config import settings
from backend.workers.worker_ai_detect import AiDetectWorker


def test_selects_only_uncertain_shots_paint_first():
    plays = [
        {"event_type": "shot", "result": "Missed", "confidence": 0.6, "shot_zone": "Paint Non-RA"},  # low-conf paint
        {"event_type": "shot", "result": "Made", "confidence": 0.95, "shot_zone": "Right Wing 3"},   # confident -> skip
        {"event_type": "shot", "result": None, "confidence": 0.9, "shot_zone": "Top of Key 3"},      # null result
        {"event_type": "possession", "result": None, "confidence": 0.3},                             # not a shot
    ]
    sel = AiDetectWorker._uncertain_bb_shots(plays, conf=0.75, max_n=8)
    idxs = [i for i, _ in sel]
    assert set(idxs) == {0, 2}          # confident make + non-shot excluded
    assert idxs[0] == 0                 # paint shaky shot re-checked first


def test_cap_respected():
    plays = [{"event_type": "shot", "result": None, "confidence": 0.1, "shot_zone": "z"} for _ in range(20)]
    assert len(AiDetectWorker._uncertain_bb_shots(plays, conf=0.75, max_n=5)) == 5


def test_flag_defaults_off():
    # Ships inert: validate cost + paint made/miss gain on a test run before enabling.
    assert settings.DETECT_FAST_RESULT_VERIFY is False
    assert settings.DETECT_FAST_RESULT_VERIFY_CONF == 0.75
    assert settings.DETECT_FAST_RESULT_VERIFY_MAX == 8
