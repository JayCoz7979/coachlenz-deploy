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


def test_unset_extra_origins_match_the_historical_list():
    # The third argument defaults empty. Calling it explicitly empty must not
    # add or remove a single origin, in production or outside it.
    for env in ("production", "staging", "test"):
        historical = build_allowed_origins("https://coachlenz.com", env)
        assert build_allowed_origins("https://coachlenz.com", env, "") == historical
        assert build_allowed_origins("https://coachlenz.com", env, "  ,  ") == historical


def test_extra_origins_are_exact_and_https_only_in_production():
    raw = "https://staging-frontend.example.com, http://staging-frontend.example.com, https://*.example.com, not-a-url"
    prod = build_allowed_origins("https://coachlenz.com", "production", raw)
    assert "https://staging-frontend.example.com" in prod
    assert "http://staging-frontend.example.com" not in prod
    assert "https://*.example.com" not in prod
    assert "not-a-url" not in prod
    # The historical hosts are still there.
    assert "https://app.coachlenz.com" in prod

    staging = build_allowed_origins("https://api.example.com", "staging", raw)
    assert "https://staging-frontend.example.com" in staging
    assert "http://staging-frontend.example.com" in staging
    assert "https://*.example.com" not in staging
