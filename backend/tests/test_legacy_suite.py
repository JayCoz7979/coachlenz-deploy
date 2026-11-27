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
import os
import re
import sys
import base64
import subprocess
import tempfile
import pathlib

import pytest

# Repo root (the dir that holds the `backend` package), from this file's location:
# .../backend/tests/test_legacy_suite.py -> parents[2].
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SUITE_MODULE = "backend.tests.test_api_integration"
_SUCCESS_MARKER = "ALL API INTEGRATION TESTS PASSED"
_SUMMARY_RE = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")
_RUN_TIMEOUT_SECONDS = 240


def _fernet_key() -> str:
    """A valid Fernet key (32 url-safe-base64 bytes) made with the stdlib only, so
    this module imports without the `cryptography` package at collection time."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def _itest_child_env(tmpdir: str) -> dict:
    """Explicit, test-only environment for the child: SQLite, placeholder secrets, a
    fresh encryption key, the repo root on PYTHONPATH, and the unique temp dir for
    every temp-dir variable. No inherited production DATABASE_URL/credential survives."""
    env = dict(os.environ)
    db_path = pathlib.Path(tmpdir) / "coachlenz_itest.db"
    env.update({
        # Steer tempfile.gettempdir() (and thus the suite's DB) into the unique dir.
        "TMPDIR": tmpdir,
        "TMP": tmpdir,
        "TEMP": tmpdir,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}",
        "SECRET_KEY": "itest-bridge-secret",
        "ANTHROPIC_API_KEY": "itest-bridge-placeholder",
        "FERNET_KEY": _fernet_key(),
        "PYTHONPATH": str(_REPO_ROOT),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _run_itest_child(args, env, cwd, timeout):
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
    )


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
    """Execute the real ASGI/SQLite API suite in an isolated child process and require
    genuine success.

    The suite's entrypoint is `async def run()`, so the old `mod.run()` call here
    returned an un-awaited coroutine and the suite never executed (a false green).
    This drives it as a module in a clean child instead, so the lane runs real
    checks. A timeout, missing deps, nonzero exit, a missing success marker, or a
    zero/failed summary all fail; none can pass silently.
    """
    with tempfile.TemporaryDirectory(prefix="coachlenz_itest_") as tmpdir:
        tmp_real = os.path.realpath(tmpdir)
        env = _itest_child_env(tmpdir)

        # Confirm the child's temp dir resolves to THIS unique directory before the
        # suite touches any DB file, so the shared system coachlenz_itest.db is never
        # read or deleted.
        try:
            pre = _run_itest_child(
                ["-c", "import tempfile, os; print(os.path.realpath(tempfile.gettempdir()))"],
                env=env, cwd=tmpdir, timeout=30,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("Temp-dir pre-check timed out before the suite could run.")
        resolved = (pre.stdout or "").strip()
        print(f"[itest-bridge] child gettempdir -> {resolved!r} (expected {tmp_real!r})")
        assert pre.returncode == 0, f"temp pre-check failed rc={pre.returncode}\n{pre.stderr}"
        assert resolved == tmp_real, (
            "Child temp dir did not isolate to the unique directory; refusing to run "
            f"the suite. resolved={resolved!r} expected={tmp_real!r}"
        )

        try:
            proc = _run_itest_child(["-m", _SUITE_MODULE], env=env, cwd=tmpdir, timeout=_RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pytest.fail(f"Integration suite timed out after {_RUN_TIMEOUT_SECONDS}s.")

        print("[itest-bridge] STDOUT\n" + (proc.stdout or ""))
        print("[itest-bridge] STDERR\n" + (proc.stderr or ""))

        assert proc.returncode == 0, (
            f"Integration suite exited {proc.returncode}. See STDOUT/STDERR above. "
            f"stderr tail: {(proc.stderr or '')[-800:]}"
        )
        assert _SUCCESS_MARKER in (proc.stdout or ""), (
            f"Suite did not print the success marker {_SUCCESS_MARKER!r}; an exit 0 "
            "without executed checks is not a pass."
        )
        m = _SUMMARY_RE.search(proc.stdout or "")
        assert m, "Could not find the 'N passed, M failed' summary; refusing to treat this as a pass."
        passed, failed = int(m.group(1)), int(m.group(2))
        assert passed > 0, f"Suite reported {passed} passed; no checks executed."
        assert failed == 0, f"Suite reported {failed} failed check(s)."

        isolated_db = pathlib.Path(tmpdir) / "coachlenz_itest.db"
        assert isolated_db.exists(), (
            "Expected the suite's SQLite DB inside the isolated temp dir; isolation "
            "may not have held."
        )
