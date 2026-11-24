"""
Marketing-consent contract (migration 055): the register request's opt-in field, the
per-user unsubscribe-link helper, and the unsubscribe request shape. The columns
themselves are smoke-tested by the SQLite schema build.

Signup with the box ticked used to 500 (unknown legal document "marketing") and roll
the new account back. The register test drives that path with a fake DB: no network,
no Postgres.
"""
import asyncio
import inspect
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.config import settings
from backend.models.legal import LegalAcceptance
from backend.models.user import User
from backend.routers.auth import RegisterRequest, UnsubscribeRequest, register
from backend.services import feature_flags
from backend.services.email_service import marketing_unsubscribe_url, APP_BASE
from backend.services.legal import DOCUMENT_VERSIONS


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _RegDB:
    def __init__(self):
        self.added = []

    async def execute(self, *_a, **_k):
        # No existing user with this email.
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        return None

    async def rollback(self):
        return None

    def begin_nested(self):
        return _Savepoint()


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="203.0.113.5"))


def _register(body, db, monkeypatch, request=None):
    async def _no_email(*_a, **_k):
        return None

    monkeypatch.setattr("backend.routers.auth.send_welcome_email", _no_email)
    fn = inspect.unwrap(register)
    return asyncio.run(fn(body, request or _request(), db))


@pytest.fixture
def signups_open(monkeypatch):
    """These tests exercise the opt-in path. Production stays closed."""
    monkeypatch.setattr(settings, "SIGNUPS_ENABLED", True)
    feature_flags._clear_cache()
    yield
    feature_flags._clear_cache()


@pytest.mark.unit
def test_register_marketing_opt_in_is_opt_in_only():
    # Default is False: marketing is never assumed. The box must be ticked.
    base = {"name": "Coach", "email": "c@example.com", "password": "pw12345678", "org_name": "Panthers"}
    assert RegisterRequest(**base).marketing_opt_in is False
    assert RegisterRequest(**base, marketing_opt_in=True).marketing_opt_in is True


@pytest.mark.unit
def test_unsubscribe_url_points_at_the_app_page_with_token():
    url = marketing_unsubscribe_url("abc123")
    assert url == f"{APP_BASE}/unsubscribe?token=abc123"
    # The app host serves the /unsubscribe page (same host as the reset-password link).
    assert url.startswith("https://app.coachlenz.com/unsubscribe?token=")


@pytest.mark.unit
def test_unsubscribe_request_requires_a_token():
    assert UnsubscribeRequest(token="x").token == "x"
    with pytest.raises(Exception):
        UnsubscribeRequest()  # token is required


@pytest.mark.unit
def test_signup_with_marketing_opt_in_succeeds_and_records_consent(monkeypatch, signups_open):
    db = _RegDB()
    out = _register(RegisterRequest(
        name="John Hasler",
        email="coach-opt-in@example.com",
        password="pw12345678",
        org_name="Broken Bow",
        accepted_terms=True,
        marketing_opt_in=True,
        source="hudl",
    ), db, monkeypatch)
    assert out["access_token"] and out["token_type"] == "bearer"
    user = next(obj for obj in db.added if isinstance(obj, User))
    assert user.marketing_opt_in is True
    assert user.marketing_opt_in_at is not None
    docs = [obj for obj in db.added if isinstance(obj, LegalAcceptance)]
    assert {d.document for d in docs} == {"terms", "privacy", "marketing"}
    marketing = next(d for d in docs if d.document == "marketing")
    assert marketing.version == DOCUMENT_VERSIONS["marketing"]
    assert marketing.ip_address == "203.0.113.5"
    assert marketing.user_id == user.id
    from backend.models.organization import Organization
    from backend.routers.auth import send_email_code, verify_email
    org = next(obj for obj in db.added if isinstance(obj, Organization))
    assert org.signup_source == "hudl"
    # Email verification is a later step. Signup must not mark the address verified.
    assert user.email_verified is not True
    assert send_email_code and verify_email


@pytest.mark.unit
def test_signup_without_marketing_opt_in_succeeds_and_records_no_marketing(monkeypatch, signups_open):
    db = _RegDB()
    out = _register(RegisterRequest(
        name="John Hasler",
        email="coach-opt-out@example.com",
        password="pw12345678",
        org_name="Broken Bow",
        accepted_terms=True,
        marketing_opt_in=False,
    ), db, monkeypatch)
    assert out["access_token"]
    user = next(obj for obj in db.added if isinstance(obj, User))
    assert user.marketing_opt_in is False
    assert user.marketing_opt_in_at is None
    docs = [obj.document for obj in db.added if isinstance(obj, LegalAcceptance)]
    assert "marketing" not in docs
    assert set(docs) == {"terms", "privacy"}


@pytest.mark.unit
def test_signup_stores_the_user_agent_on_legal_acceptances(monkeypatch, signups_open):
    db = _RegDB()
    long_ua = "CoachBrowser/" + ("x" * 600)
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.9"),
        headers={"user-agent": long_ua},
    )
    _register(RegisterRequest(
        name="John Hasler",
        email="coach-ua@example.com",
        password="pw12345678",
        org_name="Broken Bow",
        accepted_terms=True,
        marketing_opt_in=True,
    ), db, monkeypatch, request=request)
    rows = [obj for obj in db.added if isinstance(obj, LegalAcceptance)]
    assert {row.document for row in rows} == {"terms", "privacy", "marketing"}
    assert rows
    assert all(row.ip_address == "203.0.113.9" for row in rows)
    assert all(row.user_agent == long_ua[:512] for row in rows)
    assert all(len(row.user_agent) == 512 for row in rows)


@pytest.mark.unit
def test_signup_is_rejected_when_signups_are_off(monkeypatch):
    monkeypatch.setattr(settings, "SIGNUPS_ENABLED", False)
    feature_flags._clear_cache()
    db = _RegDB()
    with pytest.raises(HTTPException) as exc:
        _register(RegisterRequest(
            name="John Hasler",
            email="coach-closed@example.com",
            password="pw12345678",
            org_name="Broken Bow",
            accepted_terms=True,
            marketing_opt_in=True,
        ), db, monkeypatch)
    assert exc.value.status_code == 403
    assert exc.value.detail.startswith("Signups are paused")
    assert db.added == []
    assert settings.SIGNUPS_ENABLED is False


@pytest.mark.unit
def test_user_model_has_a_token_backed_unsubscribe_default():
    # Every user gets a stable unsubscribe token (so opt-out works even for a coach who
    # never opted in). The column carries a callable default that yields a real token.
    from backend.models.user import User
    default = User.__table__.c.unsubscribe_token.default
    assert default is not None and default.is_callable
    # SQLAlchemy wraps a zero-arg callable default as fn(context); pass a dummy context.
    token = default.arg(None)
    assert isinstance(token, str) and len(token) >= 20
