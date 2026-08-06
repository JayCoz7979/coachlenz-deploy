"""Finding #4b: a 2nd billable analysis on already-analyzed film returns a
needs_confirmation signal (when the flag is on) instead of silently charging, and
a confirmed re-run notifies the rest of the coaching staff."""
import asyncio
from types import SimpleNamespace

import backend.routers.ai_detect as ai


def _aret(v):
    async def _f(*_a, **_k):
        return v
    return _f


class _Result:
    def __init__(self, v):
        self.v = v

    def scalar_one_or_none(self):
        return self.v

    def scalars(self):
        items = self.v if isinstance(self.v, list) else ([] if self.v is None else [self.v])
        return SimpleNamespace(all=lambda: items)


class _FakeDB:
    def __init__(self, results):
        self._r = list(results)
        self.added = []

    async def execute(self, *_a, **_k):
        return self._r.pop(0)

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, _o):
        pass


def test_rerun_returns_needs_confirmation_when_flag_on(monkeypatch):
    monkeypatch.setattr(ai.feature_flags, "is_enabled", _aret(True))
    monkeypatch.setattr(ai, "assert_sport_allowed", lambda *a, **k: None)
    monkeypatch.setattr(ai, "assert_ready_to_analyze", lambda *a, **k: None)
    game = SimpleNamespace(id="g1", organization_id="o1", status="ready", sport="football", title="W3")
    # execute order: select Game, orphan update, existing-active, prior-done job
    db = _FakeDB([_Result(game), _Result(None), _Result(None), _Result("job-done")])
    user = SimpleNamespace(id="u1", organization_id="o1", name="Coach K")
    org = SimpleNamespace(id="o1")
    out = asyncio.run(ai.trigger_auto_detect(
        "g1", dry_run=False, mode="fast", full=False, test=False, grade=False,
        confirm_rerun=False, user=user, org=org, db=db))
    assert out["status"] == "needs_confirmation"
    assert db.added == []  # nothing queued, nothing charged


def test_notify_team_creates_notifications_for_other_coaches():
    coaches = [SimpleNamespace(id="c2"), SimpleNamespace(id="c3")]
    db = _FakeDB([_Result(coaches)])
    user = SimpleNamespace(id="c1", organization_id="o1", name="Coach K")
    game = SimpleNamespace(id="g1", title="Week 3")
    asyncio.run(ai._notify_team_of_rerun(db, user, game))
    assert len(db.added) == 2  # both OTHER coaches, not the triggerer
    assert all(n.type == "rerun" for n in db.added)
    assert db.added[0].data["game_id"] == "g1" and db.added[0].data["by"] == "c1"


def test_notify_team_noop_when_solo_coach():
    db = _FakeDB([_Result([])])   # no other coaches
    user = SimpleNamespace(id="c1", organization_id="o1", name="Solo")
    game = SimpleNamespace(id="g1", title="W3")
    asyncio.run(ai._notify_team_of_rerun(db, user, game))
    assert db.added == []


def test_guardrail_is_flag_gated():
    import inspect
    src = inspect.getsource(ai.trigger_auto_detect)
    assert 'is_enabled(db, "rerun_confirmation")' in src and "needs_confirmation" in src
