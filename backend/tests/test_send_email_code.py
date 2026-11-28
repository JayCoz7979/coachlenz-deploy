"""send-email-code must not start the resend cooldown when the email never went out.

Bug: the cooldown is derived from users.email_verify_expires. The handler wrote the
new expiry BEFORE sending, so a provider failure (502) still left a fresh expiry and
the coach's immediate retry got 429 for a minute. Now a failed send restores the
previous code + expiry.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import auth as auth_router

pytestmark = pytest.mark.unit

# slowapi wraps the endpoint; call the undecorated handler (no rate limiter in a unit test).
_handler = auth_router.send_email_code.__wrapped__


class _DB:
    def __init__(self, user):
        self.user = user
        self.commits = 0

    async def execute(self, stmt, *_a, **_k):
        # Apply the UPDATE's values to the in-memory user, like the real row.
        for col, val in stmt.compile().params.items():
            if hasattr(self.user, col):
                setattr(self.user, col, val)
        return None

    async def commit(self):
        self.commits += 1


def _user(**kw):
    base = dict(id="u1", email="coach@example.com", name="Coach", email_verified=False,
                email_verify_code_hash=None, email_verify_expires=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _send(user, db):
    return asyncio.run(_handler(request=SimpleNamespace(), user=user, db=db))


def test_failed_send_returns_502_and_retry_is_not_429(monkeypatch):
    async def _fail(*_a, **_k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(auth_router, "send_email_verification_code", _fail)
    user = _user()
    db = _DB(user)
    with pytest.raises(HTTPException) as exc:
        _send(user, db)
    assert exc.value.status_code == 502
    assert user.email_verify_expires is None          # cooldown released
    assert user.email_verify_code_hash is None

    sent = []

    async def _ok(to, name, code):
        sent.append(code)
    monkeypatch.setattr(auth_router, "send_email_verification_code", _ok)
    out = _send(user, db)                             # immediate retry: allowed
    assert out["ok"] is True and len(sent) == 1
    assert user.email_verify_expires is not None


def test_failed_resend_keeps_the_previous_valid_code(monkeypatch):
    async def _fail(*_a, **_k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(auth_router, "send_email_verification_code", _fail)
    prev_exp = datetime.utcnow() + timedelta(minutes=10)   # sent 5 min ago
    user = _user(email_verify_code_hash="prevhash", email_verify_expires=prev_exp)
    with pytest.raises(HTTPException):
        _send(user, _DB(user))
    assert user.email_verify_code_hash == "prevhash"
    assert user.email_verify_expires == prev_exp


def test_successful_send_still_starts_the_cooldown(monkeypatch):
    async def _ok(*_a, **_k):
        return None
    monkeypatch.setattr(auth_router, "send_email_verification_code", _ok)
    user = _user()
    db = _DB(user)
    _send(user, db)
    with pytest.raises(HTTPException) as exc:
        _send(user, db)
    assert exc.value.status_code == 429
