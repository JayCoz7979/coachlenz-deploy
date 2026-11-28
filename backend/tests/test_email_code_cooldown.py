"""
send-email-code must only start the resend cooldown when the email actually went
out. Before the fix, the cooldown (expiry = now+15min) was written BEFORE sending,
so a failed send (502) was followed by a 429 for a minute and the coach could not
retry. No DB, no mail provider: the DB is a stub that applies UPDATEs to an
in-memory user, and the sender is monkeypatched.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.routers.auth as auth

pytestmark = pytest.mark.unit

# The route is wrapped by the slowapi rate limiter, which needs a real Starlette
# Request. Drive the undecorated handler directly; the limiter is not under test.
_handler = getattr(auth.send_email_code, "__wrapped__", auth.send_email_code)


class _UserDB:
    """Applies each UPDATE's values to the in-memory user, like the real row."""
    def __init__(self, user):
        self.user = user
        self.commits = 0

    async def execute(self, stmt, *_a, **_k):
        for k, v in stmt.compile().params.items():
            if k in ("email_verify_code_hash", "email_verify_expires"):
                setattr(self.user, k, v)

    async def commit(self):
        self.commits += 1


def _user(**kw):
    base = dict(id="u1", email="coach@example.com", name="Coach", email_verified=False,
                email_verify_code_hash=None, email_verify_expires=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _send(user, db):
    return asyncio.run(_handler(SimpleNamespace(), user=user, db=db))


def test_failed_send_returns_502_and_does_not_start_the_cooldown(monkeypatch):
    async def fail(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(auth, "send_email_verification_code", fail)
    user = _user()
    db = _UserDB(user)
    with pytest.raises(HTTPException) as exc:
        _send(user, db)
    assert exc.value.status_code == 502
    assert user.email_verify_expires is None and user.email_verify_code_hash is None

    # Immediate retry is NOT throttled now; it sends.
    sent = []

    async def ok(to, name, code):
        sent.append(code)

    monkeypatch.setattr(auth, "send_email_verification_code", ok)
    out = _send(user, db)
    assert out["ok"] is True and len(sent) == 1
    assert user.email_verify_expires is not None


def test_failed_send_keeps_an_earlier_still_valid_code(monkeypatch):
    async def fail(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(auth, "send_email_verification_code", fail)
    earlier = datetime.utcnow() + timedelta(minutes=10)   # sent 5 min ago, outside cooldown
    user = _user(email_verify_code_hash="prevhash", email_verify_expires=earlier)
    with pytest.raises(HTTPException):
        _send(user, _UserDB(user))
    assert user.email_verify_code_hash == "prevhash"
    assert user.email_verify_expires == earlier


def test_successful_send_still_starts_the_cooldown(monkeypatch):
    async def ok(*_a, **_k):
        return None

    monkeypatch.setattr(auth, "send_email_verification_code", ok)
    user = _user()
    db = _UserDB(user)
    _send(user, db)
    with pytest.raises(HTTPException) as exc:
        _send(user, db)
    assert exc.value.status_code == 429


def test_already_verified_short_circuits(monkeypatch):
    async def boom(*_a, **_k):
        raise AssertionError("must not send")

    monkeypatch.setattr(auth, "send_email_verification_code", boom)
    out = _send(_user(email_verified=True), _UserDB(_user()))
    assert out == {"ok": True, "already_verified": True}
