"""
Integration-marked bridge that executes the real ASGI/SQLite API suite.

backend/tests/test_api_integration.py holds the real end-to-end suite (drives the
FastAPI app over httpx ASGITransport against a throwaway SQLite DB). conftest.py
deliberately keeps that file out of direct collection (collect_ignore), so the CI
"integration" lane, which runs `pytest -m integration`, had nothing to select and
pytest exited 5 (no tests collected). This bridge is the one integration-marked
test that drives that suite, so the lane runs real checks instead of erroring on an
empty selection. It is NOT turned into a trivial pass: it asserts the suite's own
success marker and a positive passed / zero failed summary.

Why a fresh child process, not an in-process import:
  conftest.py sets a Postgres DATABASE_URL and backend.models.base builds its async
  engine at import time. Importing or reloading the suite inside this pytest process
  would entangle that Postgres config with the suite's SQLite setup. Running
  `python -m backend.tests.test_api_integration` in a clean child keeps the two
  worlds apart: the child gets a SQLite-only, test-only environment and its own
  interpreter state.

Why TMPDIR / TMP / TEMP are set on the child:
  The suite stores its DB at `tempfile.gettempdir()/coachlenz_itest.db` and unlinks
  that path at startup. Changing cwd or DATABASE_URL alone does NOT move it. Only the
  temp-dir environment variables change what gettempdir() resolves to, so we point
  all three at a unique per-run directory and confirm the child resolves there BEFORE
  running the suite. That guarantees the system-wide coachlenz_itest.db is never read
  or deleted.
"""
import os
import re
import sys
import base64
import subprocess
import tempfile
import pathlib

import pytest

# Repo root (the dir that holds the `backend` package) derived from this file's own
# location: .../backend/tests/test_api_integration_bridge.py -> parents[2].
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

SUITE_MODULE = "backend.tests.test_api_integration"
SUCCESS_MARKER = "ALL API INTEGRATION TESTS PASSED"
SUMMARY_RE = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")
RUN_TIMEOUT_SECONDS = 240


def _fernet_key() -> str:
    """A valid Fernet key (32 url-safe-base64 bytes) generated with the stdlib only,
    so this module imports without the `cryptography` package at collection time."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def _child_env(tmpdir: str) -> dict:
    """An explicit, test-only environment for the child. Inherits PATH etc. so the
    interpreter runs, but forces SQLite, placeholder secrets, a fresh encryption key,
    the repo root on PYTHONPATH, and the unique temp dir for every temp-dir variable.
    No inherited production DATABASE_URL or real credential survives these overrides."""
    env = dict(os.environ)
    db_path = pathlib.Path(tmpdir) / "coachlenz_itest.db"
    env.update({
        # Steer tempfile.gettempdir() (and thus the suite's DB) into the unique dir.
        "TMPDIR": tmpdir,
        "TMP": tmpdir,
        "TEMP": tmpdir,
        # Test-only config under the exact names the suite / backend.config use.
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}",
        "SECRET_KEY": "itest-bridge-secret",
        "ANTHROPIC_API_KEY": "itest-bridge-placeholder",
        "FERNET_KEY": _fernet_key(),
        # Import the suite package from the repo root, not from cwd.
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def _run_child(args, env, cwd, timeout):
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.integration
def test_api_integration_suite_runs_and_passes():
    """Execute the real API integration suite in an isolated child process and require
    it to report genuine success. A timeout, missing deps, nonzero exit, a missing
    success marker, or a zero/failed summary all fail here; none can pass silently."""
    with tempfile.TemporaryDirectory(prefix="coachlenz_itest_") as tmpdir:
        tmp_real = os.path.realpath(tmpdir)
        env = _child_env(tmpdir)

        # Confirm the child's temp dir resolves to THIS unique directory before the
        # suite touches any DB file. If it does not, fail now so the shared system
        # coachlenz_itest.db is never read or deleted.
        try:
            pre = _run_child(
                ["-c", "import tempfile, os; print(os.path.realpath(tempfile.gettempdir()))"],
                env=env, cwd=tmpdir, timeout=30,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("Temp-dir pre-check timed out before the suite could run.")
        resolved = (pre.stdout or "").strip()
        print(f"[bridge] child gettempdir -> {resolved!r} (expected {tmp_real!r})")
        assert pre.returncode == 0, f"temp pre-check failed rc={pre.returncode}\n{pre.stderr}"
        assert resolved == tmp_real, (
            "Child temp dir did not isolate to the unique directory; refusing to run "
            f"the suite. resolved={resolved!r} expected={tmp_real!r}"
        )

        # Run the real suite as a module in the clean child.
        try:
            proc = _run_child(["-m", SUITE_MODULE], env=env, cwd=tmpdir, timeout=RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            print("[bridge] STDOUT (partial)\n" + out)
            print("[bridge] STDERR (partial)\n" + err)
            pytest.fail(f"Integration suite timed out after {RUN_TIMEOUT_SECONDS}s.")

        # Always surface the child's output so CI shows exactly what ran.
        print("[bridge] STDOUT\n" + (proc.stdout or ""))
        print("[bridge] STDERR\n" + (proc.stderr or ""))

        # A nonzero exit means the suite failed (or deps were missing, which raises
        # SystemExit with a nonzero code). Surface its decisive output, do not mask it.
        assert proc.returncode == 0, (
            f"Integration suite exited {proc.returncode}. See STDOUT/STDERR above. "
            f"stderr tail: {(proc.stderr or '')[-800:]}"
        )

        # Require the suite's own success marker AND a summary with real checks.
        assert SUCCESS_MARKER in (proc.stdout or ""), (
            f"Suite did not print the success marker {SUCCESS_MARKER!r}; an exit 0 "
            "without executed checks is not a pass."
        )
        m = SUMMARY_RE.search(proc.stdout or "")
        assert m, "Could not find the 'N passed, M failed' summary; refusing to treat this as a pass."
        passed, failed = int(m.group(1)), int(m.group(2))
        assert passed > 0, f"Suite reported {passed} passed; no checks executed."
        assert failed == 0, f"Suite reported {failed} failed check(s)."

        # The DB must have been created inside the isolated temp dir, proving the suite
        # ran against the unique SQLite file and not the shared system one.
        isolated_db = pathlib.Path(tmpdir) / "coachlenz_itest.db"
        assert isolated_db.exists(), (
            "Expected the suite's SQLite DB inside the isolated temp dir; isolation "
            "may not have held."
        )
