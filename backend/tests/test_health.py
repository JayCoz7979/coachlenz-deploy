"""
Unit test for the readiness DB ping (backend/health.py). The happy path (returns
True against a live DB) is covered in the integration suite; here we prove it
fails CLOSED — a connection error yields (False, message), which the endpoint
turns into a 503 so Railway won't promote a DB-less deploy.
"""
import asyncio
from unittest.mock import patch

import pytest

import backend.health as health


class _RaisingCtx:
    async def __aenter__(self):
        raise RuntimeError("db unreachable")

    async def __aexit__(self, *_a):
        return False


class _FakeEngine:
    def connect(self):
        return _RaisingCtx()


@pytest.mark.unit
def test_db_ready_false_on_connection_error():
    # Replace the module-level engine (its real .connect is read-only) with a fake
    # whose connection raises, and assert db_ready() fails closed.
    with patch.object(health, "engine", _FakeEngine()):
        ok, err = asyncio.run(health.db_ready())
    assert ok is False
    assert err and "db unreachable" in err
