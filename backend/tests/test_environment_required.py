"""Stage 2 round 2, LOW 1: ENVIRONMENT has no default and must be set explicitly.

It used to default to "production", so a staging service that forgot to set it ran as
production and would accept a live Stripe key. Now:
  * unset or blank ENVIRONMENT -> Settings() raises, so the API/worker refuses to start,
  * only an explicit "production" counts as production for the live-key check.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", env_value)
    # _env_file=None: never let a developer's local .env supply the value.
    return Settings(_env_file=None)


def test_unset_environment_refuses_to_load(monkeypatch):
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, None)
    assert "ENVIRONMENT" in str(exc.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_environment_refuses_to_load(monkeypatch, blank):
    with pytest.raises(ValidationError) as exc:
        _settings(monkeypatch, blank)
    assert "ENVIRONMENT is not set" in str(exc.value)


@pytest.mark.parametrize("raw,expected", [("production", "production"), (" Production ", "production"),
                                          ("staging", "staging"), ("TEST", "test")])
def test_explicit_environment_is_normalized(monkeypatch, raw, expected):
    assert _settings(monkeypatch, raw).ENVIRONMENT == expected


def test_process_refuses_to_start_without_environment(tmp_path):
    """Real start-up path: importing backend.config (which every entrypoint does) in a
    fresh interpreter with ENVIRONMENT unset exits non-zero. Runs from an empty cwd so
    no .env file can supply the value."""
    env = {k: v for k, v in os.environ.items() if k != "ENVIRONMENT"}
    env["PYTHONPATH"] = str(REPO_ROOT)
    r = subprocess.run([sys.executable, "-c", "import backend.config"], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "ENVIRONMENT" in r.stderr
    # The same import succeeds once ENVIRONMENT is set explicitly.
    env["ENVIRONMENT"] = "staging"
    ok = subprocess.run([sys.executable, "-c", "import backend.config"], cwd=tmp_path, env=env,
                        capture_output=True, text=True, timeout=60)
    assert ok.returncode == 0, ok.stderr


@pytest.mark.parametrize("env_value", ["staging", "test", "development", "prod", "production-like"])
def test_live_key_refused_unless_environment_is_exactly_production(monkeypatch, env_value):
    from backend.services import stripe_mode
    monkeypatch.setattr(stripe_mode.settings, "ENVIRONMENT", env_value)
    monkeypatch.setattr(stripe_mode.settings, "STRIPE_SECRET_KEY", "sk_live_" + "x" * 8)
    assert stripe_mode.is_production() is False
    with pytest.raises(RuntimeError) as exc:
        stripe_mode.assert_stripe_mode_safe_at_startup()
    assert "sk_live_" + "x" * 8 not in str(exc.value)  # never echoes the key


def test_live_key_allowed_only_with_explicit_production(monkeypatch):
    from backend.services import stripe_mode
    monkeypatch.setattr(stripe_mode.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(stripe_mode.settings, "STRIPE_SECRET_KEY", "sk_live_" + "x" * 8)
    stripe_mode.assert_stripe_mode_safe_at_startup()  # no raise
