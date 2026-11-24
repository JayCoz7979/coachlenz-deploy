"""Signup shutoff and waitlist capture.

New accounts are closed unless the signups_enabled flag is on. The shipped default
is closed (SIGNUPS_ENABLED unset or false). Login for an existing user, and staff
invites, stay available while it is closed. The waitlist reuses POST /leads.

Unit only: the endpoints run against a DB stub. No network and no real database.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import backend.routers.auth as auth_router
import backend.routers.funnel as funnel
import backend.routers.staff as staff
import backend.services.feature_flags as ff


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AuthDB:
    def __init__(self, first):
        self.first = first
        self.n = 0
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        self.n += 1
        return _Scalar(self.first if self.n == 1 else None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def refresh(self, _obj):
        return None


class _LeadDB:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        return _Scalar(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def _unwrap(fn):
    """Call the route body, not the slowapi limiter wrapper."""
    return getattr(fn, "__wrapped__", fn)


def _register_body(**extra):
    base = dict(
        name="Coach",
        email="newcoach@example.com",
        password="pw12345678",
        org_name="Lincoln High",
        accepted_terms=True,
    )
    base.update(extra)
    return auth_router.RegisterRequest(**base)


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="203.0.113.8"), headers={})


@pytest.mark.unit
def test_signups_flag_defaults_closed(monkeypatch):
    from backend.config import Settings
    assert Settings.model_fields["SIGNUPS_ENABLED"].default is False
    monkeypatch.setattr(ff.settings, "SIGNUPS_ENABLED", False)
    ff._clear_cache()
    assert ff.env_default("signups_enabled") is False


@pytest.mark.unit
def test_signups_read_closed_when_no_override(monkeypatch):
    monkeypatch.setattr(ff.settings, "SIGNUPS_ENABLED", False)
    ff._clear_cache()

    class _DB:
        async def execute(self, *_a, **_k):
            return _Scalar(None)

    assert asyncio.run(ff.is_enabled(_DB(), "signups_enabled")) is False


@pytest.mark.unit
def test_register_rejected_when_signups_closed(monkeypatch):
    async def _off(_db, key):
        assert key == "signups_enabled"
        return False

    monkeypatch.setattr(auth_router.feature_flags, "is_enabled", _off)
    db = _AuthDB(None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_unwrap(auth_router.register)(_register_body(), _request(), db))
    assert exc.value.status_code == 403
    assert "Signups are paused" in exc.value.detail
    assert db.added == [] and db.commits == 0 and db.n == 0


@pytest.mark.unit
def test_register_allowed_when_signups_enabled(monkeypatch):
    async def _on(_db, key):
        assert key == "signups_enabled"
        return True

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(auth_router.feature_flags, "is_enabled", _on)
    monkeypatch.setattr(auth_router, "record_acceptance", _noop)
    monkeypatch.setattr(auth_router, "send_welcome_email", _noop)
    monkeypatch.setattr(auth_router, "hash_password", lambda _p: "hashed")
    monkeypatch.setattr("backend.services.funnel.record_event", _noop)
    monkeypatch.setattr("backend.services.credits.grant_welcome", _noop)

    db = _AuthDB(None)
    out = asyncio.run(_unwrap(auth_router.register)(_register_body(), _request(), db))
    assert out["token_type"] == "bearer"
    assert out["access_token"] and out["refresh_token"]
    assert db.commits >= 1
    assert any(getattr(row, "email", None) == "newcoach@example.com" for row in db.added)


@pytest.mark.unit
def test_login_still_works_when_signups_closed(monkeypatch):
    async def _forbid(*_a, **_k):
        raise AssertionError("login must not consult the signup flag")

    monkeypatch.setattr(auth_router.feature_flags, "is_enabled", _forbid)
    monkeypatch.setattr(auth_router, "verify_password", lambda pw, _hashed: pw == "correct-horse")
    user = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        organization_id="22222222-2222-2222-2222-222222222222",
        email="coach@example.com",
        hashed_password="x",
        is_active=True,
        token_version=1,
    )
    out = asyncio.run(_unwrap(auth_router.login)(
        SimpleNamespace(),
        auth_router.LoginRequest(email="coach@example.com", password="correct-horse"),
        _AuthDB(user),
    ))
    assert out["token_type"] == "bearer"
    assert out["access_token"] and out["refresh_token"]


@pytest.mark.unit
def test_staff_invite_still_works_when_signups_closed(monkeypatch):
    """Invites create the user in POST /staff/invite. They must not go through
    /auth/register, which is the endpoint the shutoff rejects."""
    async def _register_must_not_run(*_a, **_k):
        raise AssertionError("staff invite must not call /auth/register")

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(ff.settings, "SIGNUPS_ENABLED", False)
    monkeypatch.setattr(auth_router, "register", _register_must_not_run)
    monkeypatch.setattr(staff, "send_staff_invite_email", _noop)
    monkeypatch.setattr(staff, "hash_password", lambda _p: "hashed")

    body = staff.InviteIn(email="assistant@school.edu", name="Assistant", role="analyst")
    inviter = SimpleNamespace(id="inv1", organization_id="o1", name="Head Coach", role="head_coach")
    org = SimpleNamespace(id="o1", name="Lincoln High")
    db = _AuthDB(None)  # no existing user with that email
    out = asyncio.run(staff.invite_staff(body, inviter=inviter, org=org, db=db))
    assert out["invited"] is True
    assert db.added and db.added[0].email == "assistant@school.edu"


@pytest.mark.unit
def test_public_signup_status_reports_the_flag(monkeypatch):
    async def _off(_db, key):
        assert key == "signups_enabled"
        return False

    monkeypatch.setattr(auth_router.feature_flags, "is_enabled", _off)
    out = asyncio.run(auth_router.signup_status(db=None))
    assert out == {"signups_enabled": False}


def _lead(coro_body, db):
    return asyncio.run(_unwrap(funnel.capture_lead)(coro_body, SimpleNamespace(), db))


@pytest.mark.unit
def test_waitlist_email_only():
    db = _LeadDB()
    out = _lead(funnel.LeadIn(email="coach@school.edu"), db)
    assert out == {"ok": True}
    assert db.commits == 1 and len(db.added) == 1
    row = db.added[0]
    assert row.email == "coach@school.edu"
    assert row.school is None and row.sport is None
    assert row.source == "landing"


@pytest.mark.unit
def test_waitlist_all_fields():
    db = _LeadDB()
    out = _lead(funnel.LeadIn(
        email="Coach@School.edu",
        school="  Lincoln High  ",
        sport="Basketball",
        source="waitlist",
    ), db)
    assert out == {"ok": True}
    row = db.added[0]
    assert row.email == "coach@school.edu"
    assert row.school == "Lincoln High"
    assert row.sport == "basketball"
    assert row.source == "waitlist"


@pytest.mark.unit
def test_waitlist_repeat_email_fills_school_and_sport():
    existing = SimpleNamespace(email="coach@school.edu", source="landing", school=None, sport=None)
    db = _LeadDB(existing)
    out = _lead(funnel.LeadIn(
        email="coach@school.edu", school="Lincoln High", sport="football", source="waitlist",
    ), db)
    assert out == {"ok": True}
    assert db.added == []
    assert existing.school == "Lincoln High" and existing.sport == "football"


@pytest.mark.unit
def test_waitlist_rejects_bad_email():
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="not-an-email")


@pytest.mark.unit
def test_waitlist_rejects_unknown_sport():
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="coach@school.edu", sport="curling")
