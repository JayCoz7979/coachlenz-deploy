"""Dead-time skip: the local motion scorer distinguishes static windows from action,
and FAILS SAFE (+inf = keep) so a scoring error never drops a real basketball window."""
import os
import tempfile

from backend.config import settings
from backend.workers.worker_ai_detect import AiDetectWorker


def _jpg(dir_, name, color):
    from PIL import Image
    p = os.path.join(dir_, name)
    Image.new("RGB", (80, 80), color).save(p, "JPEG")
    return (p, 0.0)


def test_static_window_scores_low_action_scores_high():
    with tempfile.TemporaryDirectory() as d:
        static = [_jpg(d, f"s{i}.jpg", (120, 120, 120)) for i in range(4)]        # identical frames
        action = [_jpg(d, "a0.jpg", (0, 0, 0)), _jpg(d, "a1.jpg", (255, 255, 255)),
                  _jpg(d, "a2.jpg", (0, 0, 0)), _jpg(d, "a3.jpg", (255, 255, 255))]  # flipping
        s_static = AiDetectWorker._batch_motion_score(static)
        s_action = AiDetectWorker._batch_motion_score(action)
        assert s_static < 1.0          # near-zero motion
        assert s_action > 100.0        # big frame-to-frame change
        assert s_static < s_action


def test_unscorable_batch_fails_safe_to_inf():
    # Missing file / too few frames -> +inf so the window is KEPT, never skipped.
    assert AiDetectWorker._batch_motion_score([("/no/such/frame.jpg", 0.0)]) == float("inf")
    assert AiDetectWorker._batch_motion_score([]) == float("inf")


def test_flag_defaults_off():
    assert settings.DETECT_DEADTIME_SKIP is False
    assert settings.DETECT_DEADTIME_MOTION_MIN == 2.0
