"""
Report failure classification + status (pure) and the retry endpoint (DB stub).
Coach never sees the raw reason; founder-facing reason is classified for alerting.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.report_failures import (
    report_status, is_quota_error, failure_reason, CLIENT_FAILURE_MESSAGE,
)
from backend.routers.reports import retry_report


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_report_status_transitions():
    assert report_status("2026-07-30T00:00:00", None) == "ready"
    assert report_status(None, "boom") == "failed"
    assert report_status(None, None) == "generating"
    # A generated report with a stale error_reason is still ready (success wins).
    assert report_status("2026-07-30T00:00:00", "old error") == "ready"


def test_is_quota_error_matches_the_anthropic_limit_message():
    msg = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
           "'message': 'You have reached your specified API usage limits. You will regain "
           "access on 2026-08-01 at 00:00 UTC.'}}")
    assert is_quota_error(msg) is True
    assert is_quota_error("rate limit exceeded") is True
    assert is_quota_error("insufficient credit balance") is True
    assert is_quota_error("connection reset by peer") is False
    assert is_quota_error(None) is False


def test_failure_reason_is_concise_and_capped():
    assert failure_reason(ValueError("nope")) == "nope"
    assert failure_reason(RuntimeError("")) == "RuntimeError"  # empty message -> class name
    assert len(failure_reason(RuntimeError("x" * 5000))) <= 500


def test_client_message_leaks_no_internal_detail():
    # The coach-facing string must not mention API/limit/billing internals.
    low = CLIENT_FAILURE_MESSAGE.lower()
    assert "try again" in low
    for leak in ("api", "anthropic", "limit", "quota", "credit", "token"):
        assert leak not in low


# ── retry endpoint (DB stub) ──────────────────────────────────────────────────
class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.committed = False

    async def execute(self, *_a, **_k):
        self.executes = getattr(self, "executes", 0) + 1
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _user(org="o1"):
    return SimpleNamespace(id="u1", organization_id=org)


def _org(oid="o1"):
    return SimpleNamespace(id=oid, is_trial=False)


def _report(**kw):
    base = dict(id="r1", organization_id="o1", generated_at=None, error_reason="boom")
    base.update(kw)
    return SimpleNamespace(**base)


def test_retry_missing_report_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(retry_report("missing", user=_user(), org=_org(), db=_FakeDB([_Result(None)])))
    assert exc.value.status_code == 404


def test_retry_failed_report_clears_error_and_enqueues_job():
    rep = _report(generated_at=None, error_reason="You have reached your specified API usage limits")
    # Two execute results: the report SELECT, then the chat-reset DELETE (§13).
    db = _FakeDB([_Result(rep), _Result(None)])
    out = asyncio.run(retry_report("r1", user=_user(), org=_org(), db=db))
    assert out["status"] == "generating"
    assert rep.error_reason is None            # failure cleared
    assert db.added and db.added[0].job_type == "report"   # fresh job queued
    assert db.committed is True
    assert db.executes == 2                     # SELECT + chat-reset DELETE issued


def test_retry_already_generated_is_noop():
    rep = _report(generated_at="2026-07-30T00:00:00", error_reason=None)
    db = _FakeDB([_Result(rep)])
    out = asyncio.run(retry_report("r1", user=_user(), org=_org(), db=db))
    assert out["status"] == "ready"
    assert db.added == []                        # nothing re-queued
