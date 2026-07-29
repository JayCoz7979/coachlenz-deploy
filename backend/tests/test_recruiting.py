"""
Track 5.2 - Recruiting Board: opt-in, share-link expiry, public no-login profile,
and marking highlights. Driven with a DB stub + monkeypatched email (no network).
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.routers.recruiting as rec


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        items = self.value if isinstance(self.value, list) else ([] if self.value is None else [self.value])
        return SimpleNamespace(all=lambda: items)


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *_a, **_k):
        return self._results.pop(0)

    async def commit(self):
        return None


def _player(**kw):
    base = dict(id="p1", organization_id="o1", first_name="Darius", last_name="M",
                position="QB", grade_year="2026", jersey_number="7",
                recruiting_enabled=False, recruiting_token=None, recruiting_expires_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _coach():
    return SimpleNamespace(id="c1", organization_id="o1", name="Coach K")


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    async def _noop(*_a, **_k):
        return None
    monkeypatch.setattr(rec, "send_recruiting_profile_email", _noop)


# ── clamp ────────────────────────────────────────────────────────────────────
def test_recruiting_days_default_and_max():
    assert rec.clamp_recruiting_days(30) == 30
    assert rec.clamp_recruiting_days(None) == 30
    assert rec.clamp_recruiting_days(200) == 90   # capped
    assert rec.clamp_recruiting_days(0) == 1


# ── opt-in / share ───────────────────────────────────────────────────────────
def test_scout_link_expires_at_30_days_by_default():
    p = _player()
    out = asyncio.run(rec.enable_recruiting("p1", rec.EnableIn(), coach=_coach(), db=_FakeDB([_Result(p)])))
    assert out["expires_in_days"] == 30
    assert p.recruiting_enabled is True and p.recruiting_token
    # ~30 days out.
    assert p.recruiting_expires_at > datetime.utcnow() + timedelta(days=29)


def test_recruiting_opt_in_required_per_player():
    # Sending to a scout before enabling is refused.
    p = _player(recruiting_enabled=False, recruiting_token=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rec.send_to_scout("p1", rec.SendIn(scout_email="scout@school.edu"),
                                      coach=_coach(), org=SimpleNamespace(name="Test HS"),
                                      db=_FakeDB([_Result(p)])))
    assert exc.value.status_code == 403


def test_send_to_scout_after_enable_ok():
    p = _player(recruiting_enabled=True, recruiting_token="tok")
    out = asyncio.run(rec.send_to_scout("p1", rec.SendIn(scout_email="scout@school.edu"),
                                        coach=_coach(), org=SimpleNamespace(name="Test HS"),
                                        db=_FakeDB([_Result(p)])))
    assert out["sent_to"] == "scout@school.edu"


# ── highlights ───────────────────────────────────────────────────────────────
def test_recruiting_highlight_queues_for_board():
    p = _player()
    clip = SimpleNamespace(id="cl1", organization_id="o1", recruiting_player_id=None)
    out = asyncio.run(rec.mark_highlight(rec.MarkIn(clip_id="cl1", player_id="p1"),
                                         coach=_coach(), db=_FakeDB([_Result(p), _Result(clip)])))
    assert out["ok"] is True
    assert clip.recruiting_player_id == "p1"   # now on the board for this player


# ── public profile ───────────────────────────────────────────────────────────
def test_scout_link_no_login_required():
    p = _player(recruiting_enabled=True, recruiting_token="tok",
                recruiting_expires_at=datetime.utcnow() + timedelta(days=10))
    clips = [SimpleNamespace(id="cl1", title="TD run", start_time=1.0, end_time=6.0, r2_url="u")]
    out = asyncio.run(rec.public_profile("tok", db=_FakeDB([_Result(p), _Result(clips)])))
    assert out["shared"] is True
    assert out["name"] == "Darius M"           # name IS shown (opt-in recruiting)
    assert out["stats"]["highlights_count"] == 1


def test_public_profile_expired_is_410():
    p = _player(recruiting_enabled=True, recruiting_token="tok",
                recruiting_expires_at=datetime.utcnow() - timedelta(minutes=1))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rec.public_profile("tok", db=_FakeDB([_Result(p)])))
    assert exc.value.status_code == 410


def test_public_profile_bad_token_is_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rec.public_profile("nope", db=_FakeDB([_Result(None)])))
    assert exc.value.status_code == 404
