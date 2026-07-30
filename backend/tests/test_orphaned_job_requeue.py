"""
Worker resilience: a report job orphaned by a restart recovers fast, and a job
that's dead-lettered marks the report failed instead of leaving it spinning.

The watchdog's SQL reclaim itself is exercised by the integration path; here we
cover the tunable threshold and the dead-letter -> report-failure hook.
"""
import asyncio
from types import SimpleNamespace

from backend.services.report_failures import dead_letter_reason
from backend.workers.base import BaseWorker, STUCK_THRESHOLD_MINUTES
import backend.workers.worker_reports as wr


# ── dead_letter_reason (pure) ─────────────────────────────────────────────────
def test_dead_letter_reason_skips_a_succeeded_report():
    assert dead_letter_reason(None, "2026-07-30T00:00:00", "gave up") is None


def test_dead_letter_reason_keeps_handles_specific_reason():
    # handle() already recorded the real reason; the generic give-up must not clobber it.
    assert dead_letter_reason("You have reached your specified API usage limits", None, "gave up") \
        == "You have reached your specified API usage limits"


def test_dead_letter_reason_falls_back_to_reason_then_generic():
    assert dead_letter_reason(None, None, "boom") == "boom"
    generic = dead_letter_reason(None, None, None)
    assert "could not be generated" in generic


# ── reclaim threshold ─────────────────────────────────────────────────────────
def test_reports_reclaim_faster_than_the_conservative_default():
    assert BaseWorker.stuck_threshold_minutes == STUCK_THRESHOLD_MINUTES  # base = conservative
    assert wr.ReportsWorker.stuck_threshold_minutes < STUCK_THRESHOLD_MINUTES
    assert wr.ReportsWorker.stuck_threshold_minutes == 4


# ── on_dead_letter -> report failure ──────────────────────────────────────────
class _FakeSession:
    def __init__(self, report):
        self._report = report
        self.committed = False

    async def get(self, _model, _id):
        return self._report

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


def _run_dead_letter(monkeypatch, report, payload, reason="gave up after 3 attempts"):
    session = _FakeSession(report)
    monkeypatch.setattr(wr, "AsyncSessionLocal", lambda: session)
    asyncio.run(wr.ReportsWorker().on_dead_letter(payload, reason))
    return session


def test_on_dead_letter_marks_an_unrecorded_report_failed(monkeypatch):
    report = SimpleNamespace(error_reason=None, generated_at=None)
    session = _run_dead_letter(monkeypatch, report, {"report_id": "r1"})
    assert report.error_reason == "gave up after 3 attempts"
    assert session.committed is True


def test_on_dead_letter_leaves_a_generated_report_alone(monkeypatch):
    report = SimpleNamespace(error_reason=None, generated_at="2026-07-30T00:00:00")
    session = _run_dead_letter(monkeypatch, report, {"report_id": "r1"})
    assert report.error_reason is None
    assert session.committed is False


def test_on_dead_letter_no_report_id_is_a_noop(monkeypatch):
    called = {"n": 0}
    def _boom():
        called["n"] += 1
        raise AssertionError("should not open a session without a report_id")
    monkeypatch.setattr(wr, "AsyncSessionLocal", _boom)
    asyncio.run(wr.ReportsWorker().on_dead_letter({}, "reason"))
    assert called["n"] == 0
