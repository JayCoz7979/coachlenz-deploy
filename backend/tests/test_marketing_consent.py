"""
Marketing-consent contract (migration 055): the register request's opt-in field, the
per-user unsubscribe-link helper, and the unsubscribe request shape. Pure — no DB or
web stack. The columns themselves are smoke-tested by the SQLite schema build, and the
endpoint behavior mirrors the proven terms/privacy capture.
"""
import pytest

from backend.routers.auth import RegisterRequest, UnsubscribeRequest
from backend.services.email_service import marketing_unsubscribe_url, APP_BASE


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
def test_user_model_has_a_token_backed_unsubscribe_default():
    # Every user gets a stable unsubscribe token (so opt-out works even for a coach who
    # never opted in). The column carries a callable default that yields a real token.
    from backend.models.user import User
    default = User.__table__.c.unsubscribe_token.default
    assert default is not None and default.is_callable
    # SQLAlchemy wraps a zero-arg callable default as fn(context); pass a dummy context.
    token = default.arg(None)
    assert isinstance(token, str) and len(token) >= 20
