"""
Report-scoped AI Coach Chat (Engine §13).

Covers the grounding guarantees (no fabrication, real cutups only), the cost
measurement, and the router's isolation + ready-gating — all driven with
asyncio.run against DB/LLM stubs (no real database, no real Anthropic call).
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services import report_chat as chat
from backend.routers import report_chat as router
from backend.routers.report_chat import get_chat, ask_chat, ChatAsk


# ── stubs ────────────────────────────────────────────────────────────────────
class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _Scalars(self._items)

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


class _FakeDB:
    """Returns a queued result list per execute() call, records adds/commits."""
    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.committed = False
        self.deleted = False

    async def execute(self, *_a, **_k):
        items = self._results.pop(0) if self._results else []
        return _Result(items)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.committed = True


def _report(**kw):
    base = dict(id="r1", organization_id="o1", sport="football", report_type="opponent",
                title="Eagles Scout", prose_sections=[{"heading": "Run Game", "body": "They pound it."}],
                summary_json=None, game_ids=[], generated_at=datetime.utcnow())
    base.update(kw)
    return SimpleNamespace(**base)


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


def _org():
    return SimpleNamespace(id="o1")


def _event(**kw):
    base = dict(event_type="pass", time_seconds=120.0, down=3, distance=8,
                formation="GUN", play_type="pass", coverage=None, player="7",
                result="complete", clip_id="c1")
    base.update(kw)
    return SimpleNamespace(**base)


def _fake_message(text, usage=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=usage,
    )


# ── cutups: only real, anchored plays get an id ──────────────────────────────
def test_build_cutups_skips_meta_and_untimed_and_ids_sequentially():
    events = [
        _event(event_type="scout_meta"),          # bookkeeping — skip
        _event(time_seconds=None),                 # no anchor — skip
        _event(event_type="run", time_seconds=30.0, player="22"),
        _event(event_type="pass", time_seconds=95.0, player="7"),
    ]
    cutups = chat.build_cutups(events)
    assert [c["id"] for c in cutups] == [1, 2]
    assert cutups[0]["event_type"] == "run" and cutups[0]["clip_id"] == "c1"
    assert "t=30s" in cutups[0]["label"] and "#22" in cutups[0]["label"]


def test_build_context_includes_sections_data_and_cutups():
    rep = _report()
    cutups = chat.build_cutups([_event()])
    ctx = chat.build_report_context(rep, {"run_pass": {"pass_pct": 0.7}}, cutups)
    assert "Run Game" in ctx and "They pound it." in ctx    # coach layer
    assert "pass_pct" in ctx                                 # tendency/heat data
    assert "[1]" in ctx                                      # numbered cutup


# ── cost to 6 decimals ───────────────────────────────────────────────────────
def test_cost_usd_six_decimals():
    usage = SimpleNamespace(input_tokens=1000, output_tokens=500,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    # (1000*3.0 + 500*15.0) / 1e6 = 0.0105
    assert chat.cost_usd(usage) == 0.0105
    assert chat.cost_usd(None) == 0.0


# ── tolerant parse: never fabricate on garbage ───────────────────────────────
def test_parse_fenced_and_prose_wrapped():
    fenced = '```json\n{"answered": true, "answer": "Sit on the sticks.", "confidence": 0.8, "cutup_ids": [1]}\n```'
    p = chat._parse_answer(fenced)
    assert p["answered"] and p["cutup_ids"] == [1] and p["confidence"] == 0.8

    prose = 'Sure! {"answered": true, "answer": "Blitz.", "confidence": 0.9, "cutup_ids": []} hope it helps'
    assert chat._parse_answer(prose)["answered"] is True


def test_parse_garbage_and_empty_answer_are_not_answered():
    assert chat._parse_answer("the model rambled")["answered"] is False
    empty = '{"answered": true, "answer": "", "confidence": 0.7}'
    assert chat._parse_answer(empty)["answered"] is False   # answered w/o text != answer


# ── answer_question: grounding + cutup resolution + escalation ───────────────
def _patch_client(monkeypatch, text, usage=None):
    async def _create(**_k):
        return _fake_message(text, usage)
    monkeypatch.setattr(chat, "client",
                        SimpleNamespace(messages=SimpleNamespace(create=_create)))


def test_answer_resolves_only_real_cutups(monkeypatch):
    cutups = chat.build_cutups([_event(event_type="run", time_seconds=10.0),
                                _event(event_type="pass", time_seconds=20.0)])
    # Model cites id 1 (real) and 99 (hallucinated) — 99 must be dropped.
    _patch_client(monkeypatch,
                  '{"answered": true, "answer": "Load the box.", "confidence": 0.85, "cutup_ids": [1, 99]}')
    out = asyncio.run(chat.answer_question(report_context="ctx", cutups=cutups, history=[], question="q"))
    assert out["answered"] and out["content"] == "Load the box."
    assert [c["id"] for c in out["cutups"]] == [1]          # 99 dropped
    assert out["needs_review"] is False


def test_low_confidence_answer_flagged_for_review(monkeypatch):
    _patch_client(monkeypatch,
                  '{"answered": true, "answer": "Maybe stunt.", "confidence": 0.5, "cutup_ids": []}')
    out = asyncio.run(chat.answer_question(report_context="ctx", cutups=[], history=[], question="q"))
    assert out["answered"] and out["needs_review"] is True   # 0.5 < 0.65 escalation


def test_ungrounded_question_returns_canonical_line(monkeypatch):
    _patch_client(monkeypatch, '{"answered": false, "answer": "", "confidence": 0.2, "cutup_ids": [1]}')
    out = asyncio.run(chat.answer_question(report_context="ctx", cutups=[], history=[], question="q"))
    assert out["answered"] is False
    assert out["content"] == chat.NOT_IN_FILM               # deterministic, not fabricated
    assert out["cutups"] == []                              # no invented cutups leak through


# ── router: isolation + ready gate ───────────────────────────────────────────
def test_ask_foreign_report_is_404():
    # _load_owned_report SELECT returns nothing -> report isn't the caller's.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ask_chat("r1", ChatAsk(question="what do they run?"),
                             user=_user(), org=_org(), db=_FakeDB([[]])))
    assert exc.value.status_code == 404


def test_ask_report_still_generating_is_409():
    rep = _report(generated_at=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ask_chat("r1", ChatAsk(question="q"),
                             user=_user(), org=_org(), db=_FakeDB([[rep]])))
    assert exc.value.status_code == 409


def test_ask_empty_question_is_422():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ask_chat("r1", ChatAsk(question="   "),
                             user=_user(), org=_org(), db=_FakeDB([[_report()]])))
    assert exc.value.status_code == 422


def test_ask_happy_path_persists_both_turns(monkeypatch):
    async def _fake_answer(**_k):
        return {"content": "Sit on the sticks.", "answered": True, "confidence": 0.8,
                "cutups": [{"id": 1, "label": "t=120s | pass"}], "cost_usd": 0.001234,
                "needs_review": False}

    async def _noop_log(**_k):
        return None

    monkeypatch.setattr(router.chat, "answer_question", _fake_answer)
    monkeypatch.setattr(router, "log_agent_action", _noop_log)

    db = _FakeDB([[_report()], [], []])   # report lookup, events, history
    out = asyncio.run(ask_chat("r1", ChatAsk(question="3rd and long?"),
                               user=_user(), org=_org(), db=db))
    # Two rows persisted: the coach question and the assistant answer.
    roles = [r.role for r in db.added]
    assert roles == ["user", "assistant"]
    assert db.committed is True
    assert out["answer"]["content"] == "Sit on the sticks."
    # UATP cost recorded to 6 decimals on the assistant row.
    assert db.added[1].total_cost_usd == 0.001234
    assert db.added[1].answered is True
