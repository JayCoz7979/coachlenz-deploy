"""Finding #20: the localhost dev origin must not be in the production CORS
allow-list (it's reflected with credentials, i.e. attack surface)."""
from backend.cors_config import build_allowed_origins


def test_localhost_excluded_in_production():
    origins = build_allowed_origins("https://coachlenz.com", "production")
    assert "http://localhost:3000" not in origins
    assert "https://app.coachlenz.com" in origins  # real origins still allowed


def test_localhost_included_outside_production():
    for env in ("development", "test", "staging"):
        assert "http://localhost:3000" in build_allowed_origins("https://coachlenz.com", env)


def test_unset_app_url_is_dropped():
    assert "" not in build_allowed_origins("", "production")


def test_origins_are_deduped():
    origins = build_allowed_origins("https://coachlenz.com", "production")
    assert len(origins) == len(set(origins))
