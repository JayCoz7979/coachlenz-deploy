"""The rate limiter must use shared Redis storage when REDIS_URL is set, so
multi-worker limits are enforced globally instead of per-process — and must fall
back to in-memory (never crash) when Redis is absent or unreachable."""
import backend.ratelimit as rl


def test_redis_uri_is_wired_to_the_limiter(monkeypatch):
    captured = {}

    class _FakeLimiter:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(rl, "Limiter", _FakeLimiter)
    rl._build_limiter("redis://h:6379/0")
    assert captured.get("storage_uri") == "redis://h:6379/0"
    assert captured.get("in_memory_fallback_enabled") is True


def test_no_uri_uses_in_memory(monkeypatch):
    captured = {}

    class _FakeLimiter:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(rl, "Limiter", _FakeLimiter)
    rl._build_limiter(None)
    assert "storage_uri" not in captured  # default (in-memory) storage


def test_redis_construction_failure_falls_back_not_crash(monkeypatch):
    # If the Redis-backed Limiter can't be built (unreachable / missing driver),
    # the app must still get a working in-memory limiter, not raise at import.
    calls = {"n": 0}

    class _FlakyLimiter:
        def __init__(self, **kw):
            calls["n"] += 1
            if "storage_uri" in kw:
                raise RuntimeError("redis down")
            # second call (no storage_uri) is the in-memory fallback

    monkeypatch.setattr(rl, "Limiter", _FlakyLimiter)
    lim = rl._build_limiter("redis://unreachable:6379/0")
    assert isinstance(lim, _FlakyLimiter)   # returned a limiter, didn't raise
    assert calls["n"] == 2                   # tried Redis, then fell back
