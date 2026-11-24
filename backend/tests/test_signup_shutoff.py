"""Signup shutoff and waitlist capture.

New accounts are closed unless the signups_enabled flag is on. The shipped default
is closed (SIGNUPS_ENABLED unset or false). Login for an existing user, and staff
invites, stay available while it is closed. The waitlist reuses POST /leads.

Unit only: the endpoints run against a DB stub. No network and no real database.
"""
import asyncio
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

import backend.routers.admin as admin
import backend.routers.auth as auth_router
import backend.routers.funnel as funnel
import backend.routers.staff as staff
import backend.services.feature_flags as ff
from backend.services.auth import require_admin
from backend.services.waitlist_export import leads_to_csv


@pytest.fixture(autouse=True)
def _clear_signup_flag_cache():
    ff._clear_cache()
    yield
    ff._clear_cache()


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


def _waitlist(**extra):
    base = dict(
        email="coach@school.edu",
        name="Ada Lovelace",
        role="head_coach",
        source="app-waitlist",
        email_consent=True,
    )
    base.update(extra)
    return funnel.LeadIn(**base)


@pytest.mark.unit
def test_waitlist_all_fields():
    db = _LeadDB()
    out = _lead(_waitlist(
        email="Coach@School.edu",
        name="  Ada   Lovelace  ",
        school="  Lincoln High  ",
        sport="Basketball",
        role="Head Coach",
        lead_magnet="spring-checklist",
        utm_source="newsletter",
        utm_medium="email",
        utm_campaign="launch",
    ), db)
    assert out == {"ok": True}
    row = db.added[0]
    assert row.email == "coach@school.edu"
    assert row.name == "Ada Lovelace"
    assert row.school == "Lincoln High"
    assert row.sport == "basketball"
    assert row.role == "head_coach"
    assert row.role_other is None
    assert row.lead_magnet == "spring-checklist"
    assert row.utm_source == "newsletter" and row.utm_campaign == "launch"
    assert row.email_consent_version == funnel.EMAIL_CONSENT_VERSION
    assert row.email_consent_at is not None
    assert row.source == "app-waitlist"


@pytest.mark.unit
def test_waitlist_repeat_updates_only_that_rows_volunteered_fields():
    other = SimpleNamespace(
        email="other@school.edu", name="Pat", school="Other HS", sport="soccer",
        role="parent", role_other=None, source="landing", lead_magnet=None,
        utm_source=None, utm_medium=None, utm_campaign=None,
        email_consent_at=None, email_consent_version=None, created_at="keep-other",
    )
    existing = SimpleNamespace(
        email="coach@school.edu", name="Old Name", school=None, sport=None,
        role=None, role_other="stale note", source="landing", lead_magnet=None,
        utm_source=None, utm_medium=None, utm_campaign=None,
        email_consent_at=None, email_consent_version=None, created_at="keep",
    )
    db = _LeadDB(existing)
    out = _lead(_waitlist(
        name="Ada Lovelace", school="Lincoln High", sport="football",
        role="other", role_other="Film dad",
        utm_source="coach-facebook",
    ), db)
    assert out == {"ok": True}
    assert db.added == []
    assert existing.email == "coach@school.edu"
    assert existing.source == "landing"
    assert existing.created_at == "keep"
    assert existing.name == "Ada Lovelace"
    assert existing.school == "Lincoln High" and existing.sport == "football"
    assert existing.role == "other" and existing.role_other == "Film dad"
    assert existing.utm_source == "coach-facebook"
    assert existing.email_consent_version == funnel.EMAIL_CONSENT_VERSION
    assert other.name == "Pat" and other.school == "Other HS" and other.created_at == "keep-other"


@pytest.mark.unit
def test_repeat_without_consent_does_not_clear_an_existing_consent():
    existing = SimpleNamespace(
        email="coach@school.edu", name="Ada", school=None, sport=None, role="parent",
        role_other=None, source="landing", lead_magnet="keep-magnet",
        utm_source="keep", utm_medium=None, utm_campaign=None,
        email_consent_at="already", email_consent_version="2026-11-24", created_at="keep",
    )
    db = _LeadDB(existing)
    out = _lead(funnel.LeadIn(email="coach@school.edu", school="Lincoln High", source="landing"), db)
    assert out == {"ok": True}
    assert existing.email_consent_at == "already"
    assert existing.lead_magnet == "keep-magnet"
    assert existing.school == "Lincoln High"
    assert existing.name == "Ada"


@pytest.mark.unit
def test_waitlist_rejects_bad_email():
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="not-an-email")


@pytest.mark.unit
def test_waitlist_rejects_blank_and_long_names():
    with pytest.raises(ValidationError):
        _waitlist(name="   ")
    with pytest.raises(ValidationError):
        _waitlist(name="A" * 101)


@pytest.mark.unit
def test_waitlist_rejects_unknown_role_and_oversized_role_other():
    with pytest.raises(ValidationError):
        _waitlist(role="wizard")
    with pytest.raises(ValidationError):
        _waitlist(role="other", role_other="x" * 101)


@pytest.mark.unit
def test_waitlist_source_requires_name_role_and_consent():
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="coach@school.edu", source="app-waitlist", role="parent", email_consent=True)
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="coach@school.edu", source="app-waitlist", name="Ada", email_consent=True)
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="coach@school.edu", source="app-waitlist", name="Ada", role="parent", email_consent=False)


@pytest.mark.unit
def test_waitlist_rejects_unknown_sport():
    with pytest.raises(ValidationError):
        _waitlist(sport="curling")


@pytest.mark.unit
def test_lead_magnet_and_utm_are_length_capped():
    with pytest.raises(ValidationError):
        _waitlist(lead_magnet="m" * 81)
    with pytest.raises(ValidationError):
        _waitlist(utm_campaign="c" * 121)


def _http(ip: str) -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/leads",
        "raw_path": b"/leads",
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
        "server": ("test", 80),
    })


@pytest.mark.unit
def test_leads_rate_limit_is_ten_per_minute():
    body = funnel.LeadIn(email="limit@school.edu", source="landing")
    ip = "203.0.113.77"
    for _ in range(10):
        assert asyncio.run(funnel.capture_lead(body, _http(ip), _LeadDB()))["ok"] is True
    with pytest.raises(RateLimitExceeded):
        asyncio.run(funnel.capture_lead(body, _http(ip), _LeadDB()))


class _FlagDB:
    def __init__(self, flag):
        self.flag = flag
        self.n = 0
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        self.n += 1
        if isinstance(self.flag, Exception):
            raise self.flag
        return _Scalar(self.flag if self.n == 1 else None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def _expect_register_closed(db):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_unwrap(auth_router.register)(_register_body(), _request(), db))
    assert exc.value.status_code == 403
    assert "Signups are paused" in exc.value.detail
    assert db.added == []


@pytest.mark.unit
def test_register_blocked_when_no_flag_row(monkeypatch):
    monkeypatch.setattr(ff.settings, "SIGNUPS_ENABLED", False)
    _expect_register_closed(_FlagDB(None))


@pytest.mark.unit
def test_register_blocked_when_db_override_is_false(monkeypatch):
    monkeypatch.setattr(ff.settings, "SIGNUPS_ENABLED", True)
    _expect_register_closed(_FlagDB(False))


@pytest.mark.unit
def test_flag_loader_fails_closed_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(ff.settings, "SIGNUPS_ENABLED", False)
    _expect_register_closed(_FlagDB(RuntimeError("db down")))


@pytest.mark.unit
def test_forgot_reset_and_invite_acceptance_work_when_signups_are_closed(monkeypatch):
    async def _forbid(*_a, **_k):
        raise AssertionError("password reset must not read the signup flag")

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(auth_router.feature_flags, "is_enabled", _forbid)
    monkeypatch.setattr(auth_router, "send_password_reset_email", _noop)
    monkeypatch.setattr(auth_router, "hash_password", lambda _p: "new-hash")
    user = SimpleNamespace(
        email="coach@example.com", name="Coach", is_active=True,
        reset_token_hash=None, reset_token_expires=None,
        hashed_password="old", token_version=2,
    )

    class _DB:
        async def execute(self, *_a, **_k):
            return _Scalar(user)

        async def commit(self):
            return None

    forgot = asyncio.run(_unwrap(auth_router.forgot_password)(
        SimpleNamespace(), auth_router.ForgotPasswordRequest(email="coach@example.com"), _DB(),
    ))
    assert forgot["ok"] is True and user.reset_token_hash

    token = "invite-token-from-staff"
    user.reset_token_hash = auth_router._sha256(token)
    user.reset_token_expires = datetime.utcnow() + timedelta(days=6)
    reset = asyncio.run(_unwrap(auth_router.reset_password)(
        SimpleNamespace(),
        auth_router.ResetPasswordRequest(token=token, new_password="newpassword1"),
        _DB(),
    ))
    assert reset["ok"] is True
    assert user.hashed_password == "new-hash"
    assert user.reset_token_hash is None
    assert user.token_version == 3


@pytest.mark.unit
def test_admin_csv_includes_waitlist_fields_and_is_admin_gated():
    dep = inspect.signature(admin.export_waitlist_csv).parameters["user"].default
    assert getattr(dep, "dependency", None) is require_admin
    row = SimpleNamespace(
        email="coach@school.edu", name="=Ada", role="head_coach", role_other=None,
        school="Lincoln", sport="football", source="app-home", lead_magnet="checklist",
        utm_source="ig", utm_medium="social", utm_campaign="launch",
        email_consent_at=datetime(2026, 11, 24, 12, 0, 0),
        email_consent_version="2026-11-24",
        created_at=datetime(2026, 11, 24, 12, 1, 0),
    )
    other = SimpleNamespace(
        email="other@school.edu", name="Pat", role="parent", role_other=None,
        school="Other", sport=None, source="landing", lead_magnet=None,
        utm_source=None, utm_medium=None, utm_campaign=None,
        email_consent_at=None, email_consent_version=None, created_at=None,
    )
    text = leads_to_csv([row, other])
    assert text.splitlines()[0].startswith("email,name,role,")
    assert "email_consent_version" in text.splitlines()[0]
    assert "lead_magnet" in text.splitlines()[0]
    assert "'=Ada" in text
    assert "coach@school.edu" in text and "other@school.edu" in text
