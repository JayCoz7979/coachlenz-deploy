"""Finding #4 (refund-on-failure): a detection run that errors or dead-letters
must reverse the coach's usage charge (linked by job_id), so they are never
billed for analysis that didn't deliver."""
import asyncio
import inspect

import backend.workers.worker_ai_detect as w


class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        self._sink.append(stmt)

    async def commit(self):
        pass


def test_refund_issues_a_delete_for_the_job(monkeypatch):
    executed = []
    monkeypatch.setattr(w, "AsyncSessionLocal", lambda: _FakeSession(executed))
    asyncio.run(w.AiDetectWorker()._refund_usage("job-123"))
    assert len(executed) == 1
    assert executed[0].__class__.__name__ == "Delete"  # DELETE FROM analysis_usage ...


def test_refund_is_noop_without_a_job_id(monkeypatch):
    def _boom():
        raise AssertionError("must not open a session when job_id is None")
    monkeypatch.setattr(w, "AsyncSessionLocal", _boom)
    asyncio.run(w.AiDetectWorker()._refund_usage(None))  # returns early, no session


def test_dead_letter_refunds_the_job(monkeypatch):
    worker = w.AiDetectWorker()
    refunded = []

    async def _fake_refund(jid):
        refunded.append(jid)

    monkeypatch.setattr(worker, "_refund_usage", _fake_refund)
    monkeypatch.setattr(w, "AsyncSessionLocal", lambda: _FakeSession([]))
    asyncio.run(worker.on_dead_letter({"_job_id": "j1", "game_id": "g1"}, "gave up"))
    assert refunded == ["j1"]


def test_trigger_links_usage_to_its_job():
    import backend.routers.ai_detect as ai
    src = inspect.getsource(ai.trigger_auto_detect)
    assert "await db.flush()" in src        # job.id assigned before the usage insert
    assert "job_id=job.id" in src           # usage row carries the link for refunds


def test_failure_path_refunds_before_reraise():
    src = inspect.getsource(w.AiDetectWorker._detect_plays)
    # the except block refunds, then re-raises so base.py marks the job errored
    assert "_refund_usage(job_id)" in src
