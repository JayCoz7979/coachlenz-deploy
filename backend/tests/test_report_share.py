"""
Track 2.1 - read-only public report share links.

Covers the day clamp (7 default / 30 max) and the public view endpoint's token +
expiry gating, driven with asyncio.run against a DB stub (no real database).
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers.reports import (
    clamp_share_days, create_report_share, view_shared_report, revoke_report_share,
)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Returns the report on the first execute (the SELECT); no-ops the view-count
    UPDATE and commit."""
    def __init__(self, report):
        self._report = report
        self._calls = 0

    async def execute(self, *_a, **_k):
        self._calls += 1
        return _Result(self._report if self._calls == 1 else None)

    async def commit(self):
        return None


def _report(**kw):
    base = dict(id="r1", organization_id="o1", title="Eagles Scout", sport="football",
                report_type="opponent", prose_sections=[{"heading": "Run Game", "body": "x"}],
                summary_json=None, watermarked=False, generated_at=None,
                share_token=None, share_expires_at=None, share_view_count=0)
    base.update(kw)
    return SimpleNamespace(**base)


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


# ── day clamp ────────────────────────────────────────────────────────────────
def test_clamp_defaults_and_bounds():
    assert clamp_share_days(7) == 7
    assert clamp_share_days(1) == 1
    assert clamp_share_days(30) == 30
    assert clamp_share_days(100) == 30    # capped at 30
    assert clamp_share_days(0) == 1       # floored at 1
    assert clamp_share_days(-5) == 1
    assert clamp_share_days("nope") == 7  # unparseable -> default


# ── create ───────────────────────────────────────────────────────────────────
def test_create_share_sets_token_and_clamped_expiry():
    rep = _report()
    out = asyncio.run(create_report_share("r1", expires_in_days=100, user=_user(), db=_FakeDB(rep)))
    assert out["expires_in_days"] == 30           # clamped
    assert rep.share_token and out["share_token"] == rep.share_token
    assert rep.share_expires_at > datetime.utcnow()
    assert out["share_path"].endswith(rep.share_token)


# ── public view: token + expiry gating ───────────────────────────────────────
def test_view_valid_share_returns_payload():
    rep = _report(share_token="tok123",
                  share_expires_at=datetime.utcnow() + timedelta(days=3))
    out = asyncio.run(view_shared_report("r1", "tok123", db=_FakeDB(rep)))
    assert out["shared"] is True
    assert out["title"] == "Eagles Scout"
    assert out["sections"] and "summary" in out


def test_view_expired_share_is_410():
    rep = _report(share_token="tok123",
                  share_expires_at=datetime.utcnow() - timedelta(minutes=1))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(view_shared_report("r1", "tok123", db=_FakeDB(rep)))
    assert exc.value.status_code == 410


def test_view_unknown_token_is_404():
    # Report not found for this (id, token) pair -> DB returns None.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(view_shared_report("r1", "wrong", db=_FakeDB(None)))
    assert exc.value.status_code == 404


# ── revoke ───────────────────────────────────────────────────────────────────
def test_revoke_clears_token_and_expiry():
    rep = _report(share_token="tok123",
                  share_expires_at=datetime.utcnow() + timedelta(days=3))
    out = asyncio.run(revoke_report_share("r1", user=_user(), db=_FakeDB(rep)))
    assert out["ok"] is True
    assert rep.share_token is None and rep.share_expires_at is None
