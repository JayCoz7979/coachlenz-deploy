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
from backend.config import settings
from backend.services.auth import require_admin
from backend.services.waitlist_capture import CONSENT_PAIRS, active_consent, consent_text_sha256
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
def test_consent_pairs_store_the_line_and_the_button(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_CONSENT_PAIR", "a")
    a = active_consent()
    assert a["id"] == "a"
    assert a["version"] == "cl-waitlist-v1-a"
    assert a["button"] == "Join the waitlist"
    assert a["line"] == CONSENT_PAIRS["a"]["line"]
    assert a["text"] == a["line"] + "\nButton: " + a["button"]
    assert a["sha256"] == consent_text_sha256()

    monkeypatch.setattr(settings, "WAITLIST_CONSENT_PAIR", "b")
    b = active_consent()
    assert b["id"] == "b"
    assert b["version"] == "cl-waitlist-v1-b"
    assert b["button"] == "Send me the Halftime Sheet"
    assert b["line"].startswith("By clicking Send me the Halftime Sheet, you join the CoachLenz waitlist")
    assert b["text"] == b["line"] + "\nButton: Send me the Halftime Sheet"
    assert "Join the waitlist" not in b["text"]

    monkeypatch.setattr(settings, "WAITLIST_CONSENT_PAIR", "nope")
    assert active_consent()["id"] == "a"


@pytest.mark.unit
def test_lead_stores_the_active_pair_version(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_CONSENT_PAIR", "b")
    db = _LeadDB()
    out = _lead(_waitlist(), db)
    assert out["ok"] is True
    assert db.added[0].consent_text_version == "cl-waitlist-v1-b"


@pytest.mark.unit
def test_public_signup_status_reports_the_flag(monkeypatch):
    async def _off(_db, key):
        assert key == "signups_enabled"
        return False

    monkeypatch.setattr(auth_router.feature_flags, "is_enabled", _off)
    out = asyncio.run(auth_router.signup_status(db=None))
    assert out["signups_enabled"] is False
    assert out["player_role_enabled"] is False
    assert out["consent_pair"] == "a"
    assert out["consent_version"] == "cl-waitlist-v1-a"
    assert out["consent_button"] == "Join the waitlist"
    assert out["consent_line"].startswith("By joining, you agree")


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
        first_name="Ada",
        role="head_coach",
        source="coachlenz-app-waitlist",
    )
    base.update(extra)
    return funnel.LeadIn(**base)


@pytest.mark.unit
def test_waitlist_all_fields():
    db = _LeadDB()
    out = _lead(_waitlist(
        email="Coach@School.edu",
        first_name="  Ada  ",
        school="  Lincoln High  ",
        sport="Basketball",
        role="principal_admin",
        lead_magnet="halftime-sheet-v1",
        utm_source="newsletter",
        utm_medium="email",
        utm_campaign="launch",
        utm_content="hero",
        utm_term="film",
        referrer="example.edu",
        landing_path="/",
        ref_code="COACH1",
    ), db)
    assert out["ok"] is True
    row = db.added[0]
    assert row.email == "coach@school.edu"
    assert row.first_name == "Ada"
    assert row.school == "Lincoln High"
    assert row.sport == "basketball"
    assert row.role == "principal_admin"
    assert row.role_branch == "admin"
    assert row.consent_text_version == "cl-waitlist-v1-a"
    assert row.utm_content == "hero" and row.utm_term == "film"
    assert row.ref_code == "COACH1"
    assert row.source == "coachlenz-app-waitlist"
    assert len(db.added) == 1
    assert row.has_account is False


@pytest.mark.unit
def test_waitlist_repeat_fills_blanks_and_does_not_touch_another_row():
    other = SimpleNamespace(
        email="other@school.edu", first_name="Pat", school="Other HS", sport="soccer",
        role="parent", role_branch="general", source="landing", lead_magnet="keep",
        utm_source=None, utm_content=None, consent_text_version="cl-waitlist-v1",
        is_19_or_older=None, created_at="keep-other",
    )
    existing = SimpleNamespace(
        email="coach@school.edu", first_name="Ada", school=None, sport=None,
        role=None, role_branch=None, source="landing", lead_magnet=None,
        utm_source=None, utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None,
        referrer=None, landing_path=None, ref_code=None,
        consent_text_version=None, is_19_or_older=None, created_at="keep",
    )
    db = _LeadDB(existing)
    out = _lead(_waitlist(school="Lincoln High", utm_source="ig"), db)
    assert out["ok"] is True and db.added == []
    assert existing.first_name == "Ada"
    assert existing.school == "Lincoln High"
    assert existing.role == "head_coach" and existing.role_branch == "coach"
    assert existing.source == "landing"
    assert existing.created_at == "keep"
    assert existing.consent_text_version == "cl-waitlist-v1-a"
    assert other.first_name == "Pat" and other.school == "Other HS"


@pytest.mark.unit
def test_repeat_does_not_blank_a_stored_value():
    existing = SimpleNamespace(
        email="coach@school.edu", first_name="Ada", school="Lincoln", sport="football",
        role="parent", role_branch="general", source="landing", lead_magnet="keep-magnet",
        utm_source="keep", utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None,
        referrer=None, landing_path=None, ref_code=None,
        consent_text_version="cl-waitlist-v1", is_19_or_older=None, created_at="keep",
    )
    db = _LeadDB(existing)
    out = _lead(funnel.LeadIn(email="coach@school.edu", school="Somewhere Else", source="landing"), db)
    assert out["ok"] is True
    assert existing.school == "Lincoln"
    assert existing.first_name == "Ada"
    assert existing.lead_magnet == "keep-magnet"
    assert existing.consent_text_version == "cl-waitlist-v1"


@pytest.mark.unit
def test_ref_code_has_no_reward_side_effects():
    from backend.models.referral import Referral, ReferralCode
    from backend.services.waitlist_capture import nurture_eligible
    with_code = _LeadDB()
    _lead(_waitlist(ref_code="COACH1"), with_code)
    plain = _LeadDB()
    _lead(_waitlist(email="plain@school.edu"), plain)
    row = with_code.added[0]
    other = plain.added[0]
    assert row.ref_code == "COACH1" and other.ref_code is None
    assert len(with_code.added) == 1 and len(plain.added) == 1
    assert not isinstance(row, (Referral, ReferralCode))
    assert row.role_branch == other.role_branch
    assert nurture_eligible(row) == nurture_eligible(other)
    assert with_code.commits == plain.commits


@pytest.mark.unit
def test_under_19_player_is_stored_on_the_minor_track(monkeypatch):
    monkeypatch.setattr(funnel.settings, "WAITLIST_PLAYER_ROLE_ENABLED", True)
    db = _LeadDB()
    out = _lead(_waitlist(role="player", is_19_or_older=False), db)
    assert out["stored"] is True and out["minor"] is True
    row = db.added[0]
    assert row.role == "player"
    assert row.role_branch == "minor_track"
    assert row.is_19_or_older is False


@pytest.mark.unit
def test_player_19_or_older_follows_the_general_path(monkeypatch):
    monkeypatch.setattr(funnel.settings, "WAITLIST_PLAYER_ROLE_ENABLED", True)
    db = _LeadDB()
    out = _lead(_waitlist(role="player", is_19_or_older=True), db)
    assert out["ok"] is True and out.get("minor") is not True
    row = db.added[0]
    assert row.role_branch == "general" and row.is_19_or_older is True


@pytest.mark.unit
def test_player_role_rejected_when_flag_is_off():
    db = _LeadDB()
    with pytest.raises(HTTPException) as exc:
        _lead(_waitlist(role="player", is_19_or_older=True), db)
    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.unit
def test_waitlist_rejects_bad_email():
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="not-an-email")


@pytest.mark.unit
def test_waitlist_rejects_blank_and_long_names():
    with pytest.raises(ValidationError):
        _waitlist(first_name="   ")
    with pytest.raises(ValidationError):
        _waitlist(first_name="A" * 81)


@pytest.mark.unit
def test_waitlist_rejects_unknown_role():
    with pytest.raises(ValidationError):
        _waitlist(role="wizard")
    with pytest.raises(ValidationError):
        _waitlist(role="school_admin")


@pytest.mark.unit
def test_waitlist_source_requires_first_name_and_role():
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="coach@school.edu", source="coachlenz-app-waitlist", role="parent")
    with pytest.raises(ValidationError):
        funnel.LeadIn(email="coach@school.edu", source="coachlenz-app-waitlist", first_name="Ada")


@pytest.mark.unit
def test_waitlist_rejects_unknown_sport():
    with pytest.raises(ValidationError):
        _waitlist(sport="curling")


@pytest.mark.unit
def test_lead_magnet_and_utm_are_length_capped():
    with pytest.raises(ValidationError):
        _waitlist(lead_magnet="m" * 121)
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
        email="coach@school.edu", first_name="=Ada", role="head_coach", role_branch="coach",
        is_19_or_older=None, school="Lincoln", sport="football", source="coachlenz-app-waitlist",
        lead_magnet="halftime-sheet-v1", utm_source="ig", utm_medium="social",
        utm_campaign="launch", utm_content=None, utm_term=None, referrer=None,
        landing_path="/", ref_code=None, consent_text_version="cl-waitlist-v1",
        confirmed_at=None, unsubscribed_at=None, has_account=False,
        marketing_consent=False, created_at=datetime(2026, 11, 24, 12, 1, 0),
    )
    other = SimpleNamespace(
        email="other@school.edu", first_name="Pat", role="parent", role_branch="general",
        is_19_or_older=None, school="Other", sport=None, source="landing", lead_magnet=None,
        utm_source=None, utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None,
        referrer=None, landing_path=None, ref_code=None, consent_text_version=None,
        confirmed_at=None, unsubscribed_at=None, has_account=False, marketing_consent=False,
        created_at=None,
    )
    text = leads_to_csv([row, other])
    header = text.splitlines()[0]
    assert header.startswith("email,first_name,role,")
    assert "consent_text_version" in header and "utm_content" in header
    assert "'=Ada" in text
    assert "coach@school.edu" in text and "other@school.edu" in text
