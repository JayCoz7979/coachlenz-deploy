"""P1a: the Opus-verify knobs (the dominant deep-mode COGS dial) are config-backed and
env-tunable, with defaults that preserve current behavior."""
from backend.config import settings
from backend.workers import worker_ai_detect as w


def test_verify_knobs_exist_with_safe_defaults():
    # Defaults must match the prior hardcoded behavior (no silent recall change).
    assert settings.DETECT_VERIFY_CONFIDENCE_THRESHOLD == 0.65
    assert settings.DETECT_MAX_VERIFY_PER_BATCH == 3


def test_worker_reads_knobs_from_settings():
    # The worker constants mirror settings so an env override actually takes effect.
    assert w.VERIFY_CONFIDENCE_THRESHOLD == settings.DETECT_VERIFY_CONFIDENCE_THRESHOLD
    assert w.MAX_VERIFY_PER_BATCH == settings.DETECT_MAX_VERIFY_PER_BATCH
