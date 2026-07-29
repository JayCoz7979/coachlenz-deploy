"""
pytest bridge for the legacy `run()` / `main()` script-style tests.

The suite historically ran each file as `python -m backend.tests.test_x`. Those
files assert real behavior but expose a `run()` (or `main()`) entrypoint instead
of `test_*` functions, so pytest never collected them and CI had nothing to gate
on. This bridge drives each one as a first-class pytest case WITHOUT editing the
originals (they stay runnable as standalone scripts).

Each listed module was verified import-side-effect-free and DB-free (pure logic),
except the ASGI integration test, which spins the real app over a throwaway
SQLite DB and is marked `integration` so the fast unit gate skips it.
"""
import importlib

import pytest

# Pure-logic modules exposing run(): no DB, no network, no secrets.
LEGACY_RUN = [
    "test_sports_lock",
    "test_football_scout",
    "test_basketball_scout_validation",
    "test_concept_inference",
    "test_game_status",
    "test_hudl_unwrap",
    "test_jersey_reader",
    "test_scouting_keys",
    "test_event_player",
    "test_report_export",
    "test_scout_rbac",
]

# Pure-logic modules exposing main() instead of run().
LEGACY_MAIN = [
    "test_basketball_scout",
    "test_bball_report_sections",
]


@pytest.mark.unit
@pytest.mark.parametrize("modname", LEGACY_RUN)
def test_legacy_run(modname):
    mod = importlib.import_module(f"backend.tests.{modname}")
    mod.run()


@pytest.mark.unit
@pytest.mark.parametrize("modname", LEGACY_MAIN)
def test_legacy_main(modname):
    mod = importlib.import_module(f"backend.tests.{modname}")
    mod.main()


@pytest.mark.integration
def test_legacy_api_integration():
    # Self-contained: httpx ASGITransport against a throwaway SQLite DB.
    # Needs aiosqlite + httpx; skipped by the fast gate via the integration marker.
    mod = importlib.import_module("backend.tests.test_api_integration")
    mod.run()
