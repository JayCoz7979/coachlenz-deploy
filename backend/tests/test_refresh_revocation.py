"""
Refresh-token revocation (logout / password change / password reset).

A refresh token embeds the user's token_version at issue time; /auth/refresh
rejects it once the user's stored token_version has moved past that snapshot.
logout, change-password and reset-password each bump token_version, which
invalidates every refresh token the user holds (all devices) at once.

Runs under plain pytest (no pytest-asyncio): the async endpoint is driven with
asyncio.run against a minimal DB stub — the revocation check happens right after
the user lookup, so no real database is needed.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.auth import create_refresh_token, decode_token
from backend.routers.auth import refresh_token, RefreshRequest


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, user):
        self._user = user

    async def execute(self, *_a, **_k):
        return _Result(self._user)


def _user(token_version, uid="11111111-1111-1111-1111-111111111111",
          org="22222222-2222-2222-2222-222222222222"):
    return SimpleNamespace(id=uid, organization_id=org,
                           token_version=token_version, is_active=True)


def _refresh(token, user):
    return asyncio.run(refresh_token(RefreshRequest(refresh_token=token), _FakeDB(user)))


def test_refresh_token_embeds_version():
    token = create_refresh_token("u1", 7)
    assert decode_token(token).get("tv") == 7


def test_refresh_accepted_when_version_matches():
    token = create_refresh_token("u1", 3)
    out = _refresh(token, _user(3))
    assert "access_token" in out


def test_refresh_rejected_after_revocation():
    # Token minted at v3; user later bumped to v4 (logout / password change).
    token = create_refresh_token("u1", 3)
    with pytest.raises(HTTPException) as exc:
        _refresh(token, _user(4))
    assert exc.value.status_code == 401
    assert "sign in again" in exc.value.detail.lower()


def test_legacy_token_without_version_matches_default():
    # A token minted before this feature has no tv claim; default 0 must still match
    # a user at the default token_version 0 (no forced logout on deploy).
    import jwt
    from backend.config import settings
    from datetime import datetime, timedelta
    legacy = jwt.encode(
        {"sub": "u1", "type": "refresh", "exp": datetime.utcnow() + timedelta(days=1)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    out = _refresh(legacy, _user(0))
    assert "access_token" in out
