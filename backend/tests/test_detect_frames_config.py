"""Basketball frames-per-window is env-tunable (the linear COGS/recall knob), with
defaults that preserve current behavior."""
from backend.config import settings
from backend.workers import worker_ai_detect as w


def test_bb_frame_defaults():
    assert settings.DETECT_FRAMES_PER_WINDOW_BB_FAST == 120
    assert settings.DETECT_FRAMES_PER_WINDOW_BB_DEEP == 100


def test_worker_reads_bb_frames_from_settings():
    assert w.FRAMES_PER_WINDOW_BB_FAST == settings.DETECT_FRAMES_PER_WINDOW_BB_FAST
    assert w.FRAMES_PER_WINDOW_BB_DEEP == settings.DETECT_FRAMES_PER_WINDOW_BB_DEEP
