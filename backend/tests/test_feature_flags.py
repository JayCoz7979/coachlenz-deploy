"""Runtime feature flags: a DB override wins over the env default, absence falls
back to the env default, a DB error degrades safely, and unknown keys are rejected."""
import asyncio
from types import SimpleNamespace

import pytest

import backend.services.feature_flags as ff


class _Res:
    def __init__(self, v):
        self.v = v

    def scalar_one_or_none(self):
        return self.v

    def scalars(self):
        items = self.v if isinstance(self.v, list) else ([] if self.v is None else [self.v])
        return SimpleNamespace(all=lambda: items)


class _DB:
    def __init__(self, results):
        self._r = list(results)
        self.added = []
        self.committed = False

    async def execute(self, *_a, **_k):
        return self._r.pop(0)

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        self.committed = True


def setup_function():
    ff._clear_cache()  # isolate the per-worker cache between tests


def test_env_default_reads_settings(monkeypatch):
    monkeypatch.setattr(ff.settings, "RERUN_CONFIRMATION_ENABLED", True)
    monkeypatch.setattr(ff.settings, "RECRUITING_CONSENT_ENABLED", False)
    assert ff.env_default("rerun_confirmation") is True
    assert ff.env_default("recruiting_consent") is False
    assert ff.env_default("unknown") is False


def test_db_override_wins_over_env(monkeypatch):
    monkeypatch.setattr(ff.settings, "RERUN_CONFIRMATION_ENABLED", False)  # env off
    db = _DB([_Res(True)])                                                 # override on
    assert asyncio.run(ff.is_enabled(db, "rerun_confirmation")) is True


def test_falls_back_to_env_when_no_override(monkeypatch):
    monkeypatch.setattr(ff.settings, "RERUN_CONFIRMATION_ENABLED", True)
    db = _DB([_Res(None)])
    assert asyncio.run(ff.is_enabled(db, "rerun_confirmation")) is True


def test_db_error_degrades_to_env(monkeypatch):
    monkeypatch.setattr(ff.settings, "RECRUITING_CONSENT_ENABLED", True)

    class _Boom:
        async def execute(self, *_a, **_k):
            raise RuntimeError("db down")

    assert asyncio.run(ff.is_enabled(_Boom(), "recruiting_consent")) is True


def test_list_flags_reports_override_vs_default(monkeypatch):
    monkeypatch.setattr(ff.settings, "RERUN_CONFIRMATION_ENABLED", True)
    monkeypatch.setattr(ff.settings, "RECRUITING_CONSENT_ENABLED", False)
    override = SimpleNamespace(key="recruiting_consent", enabled=True)
    out = asyncio.run(ff.list_flags(_DB([_Res([override])])))
    by = {f["key"]: f for f in out}
    assert by["rerun_confirmation"]["enabled"] is True and by["rerun_confirmation"]["source"] == "default"
    assert by["recruiting_consent"]["enabled"] is True and by["recruiting_consent"]["source"] == "override"


def test_set_flag_rejects_unknown_key():
    with pytest.raises(ValueError):
        asyncio.run(ff.set_flag(_DB([]), "bogus", True, "u1"))


def test_set_flag_inserts_override_when_absent():
    db = _DB([_Res(None)])
    asyncio.run(ff.set_flag(db, "rerun_confirmation", False, "u1"))
    assert db.committed and len(db.added) == 1
    assert db.added[0].key == "rerun_confirmation" and db.added[0].enabled is False
