"""Findings #8 and #9 for the detection worker:
  #8 every AsyncAnthropic client must be opened with `async with` so its httpx
     connection pool is closed (the per-batch client was leaking FDs/memory).
  #9 the bulk detect passes must use the raised DETECT_MAX_TOKENS budget, and a
     max_tokens truncation must be logged instead of silently dropping plays."""
import inspect

import backend.workers.worker_ai_detect as w


_CLIENT_METHODS = ("_analyze_batch", "_grade_plays", "_read_jerseys")


def test_all_detect_clients_are_context_managed():
    for name in _CLIENT_METHODS:
        src = inspect.getsource(getattr(w.AiDetectWorker, name))
        assert "async with anthropic.AsyncAnthropic" in src, (
            f"{name} must open its client with `async with` so it is closed"
        )
        # No bare, un-closed assignment form.
        assert "client = anthropic.AsyncAnthropic" not in src, (
            f"{name} still creates an un-closed client"
        )


def test_detect_budget_is_raised():
    assert w.DETECT_MAX_TOKENS == 8192


def test_bulk_detect_passes_use_the_raised_budget():
    for name in ("_analyze_batch", "_analyze_batch_multipass", "_analyze_batch_basketball_deep"):
        src = inspect.getsource(getattr(w.AiDetectWorker, name))
        assert "DETECT_MAX_TOKENS" in src, f"{name} must pass DETECT_MAX_TOKENS to the detect call"


def test_vision_json_logs_on_truncation():
    src = inspect.getsource(w.AiDetectWorker._vision_json)
    assert 'stop_reason' in src and 'max_tokens' in src, (
        "a max_tokens truncation must be detected and logged, not silently dropped"
    )
