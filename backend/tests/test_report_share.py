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

# Real report_ids are UUIDs (the column is a Postgres uuid). The public view validates
# the format up front, so these tests use a valid uuid string for the id argument.
VALID_ID = "11111111-1111-1111-1111-111111111111"


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
    out = asyncio.run(view_shared_report(VALID_ID, "tok123", db=_FakeDB(rep)))
    assert out["shared"] is True
    # Finding #6: the public view serves a neutral, derived title, never the
    # coach's raw report.title.
    assert out["title"] == "Football Opponent Scouting Report"
    assert out["sections"] and "summary" in out


def test_public_view_does_not_leak_a_player_name_in_the_title():
    # A coach titles a player report with a minor's name; the no-login page must
    # not echo it.
    rep = _report(title="John Smith - DB breakdown", report_type="self_scout",
                  sport="basketball", share_token="tok123",
                  share_expires_at=datetime.utcnow() + timedelta(days=3))
    out = asyncio.run(view_shared_report(VALID_ID, "tok123", db=_FakeDB(rep)))
    assert "John Smith" not in out["title"]
    assert out["title"] == "Basketball Self-Scouting Report"


def test_view_expired_share_is_410():
    rep = _report(share_token="tok123",
                  share_expires_at=datetime.utcnow() - timedelta(minutes=1))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(view_shared_report(VALID_ID, "tok123", db=_FakeDB(rep)))
    assert exc.value.status_code == 410


def test_view_unknown_token_is_404():
    # Report not found for this (id, token) pair -> DB returns None.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(view_shared_report(VALID_ID, "wrong", db=_FakeDB(None)))
    assert exc.value.status_code == 404


def test_view_nonuuid_report_id_is_404_without_touching_db():
    # Regression: a non-UUID report_id (e.g. /reports/1/share/x) must 404 up front, NOT
    # reach the query (where asyncpg raises at uuid bind time -> a bare 500 in prod). The
    # guard must short-circuit BEFORE any db.execute, so this DB raises if touched.
    class _Boom:
        async def execute(self, *_a, **_k):
            raise AssertionError("DB must not be queried for a malformed report_id")

    for bad in ("1", "not-a-uuid", "r1", ""):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(view_shared_report(bad, "tok", db=_Boom()))
        assert exc.value.status_code == 404


# ── revoke ───────────────────────────────────────────────────────────────────
def test_revoke_clears_token_and_expiry():
    rep = _report(share_token="tok123",
                  share_expires_at=datetime.utcnow() + timedelta(days=3))
    out = asyncio.run(revoke_report_share("r1", user=_user(), db=_FakeDB(rep)))
    assert out["ok"] is True
    assert rep.share_token is None and rep.share_expires_at is None
