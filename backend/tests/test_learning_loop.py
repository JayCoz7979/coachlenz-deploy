"""
Per-account learning loop (Engine §14).

The scoring / proposal / apply logic is pure and gets the bulk of the coverage;
the async write path and the coach-facing router are exercised against DB stubs
(no real database).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services import learning_loop as ll
from backend.routers import learning as learn_router
from backend.routers.learning import (
    accept_adjustment, reject_adjustment, reset_adjustment, set_manual_mode, ManualMode,
)


# ── signal classification ────────────────────────────────────────────────────
def test_classify_signal_buckets():
    assert ll.classify_signal(None, "Cover 3") == "high"        # added specificity
    assert ll.classify_signal("Cover 3", None) == "low"         # removed detail (misclick)
    assert ll.classify_signal("Cover 3", "Cover 2") == "reclass"
    assert ll.classify_signal("Cover 3", "cover 3") is None     # normalized-equal, no change
    assert ll.classify_signal("#7", "7") is None                # jersey normalization
    assert ll.classify_signal(None, None) is None
    assert ll.classify_signal("unknown", None) is None          # empty synonyms


def test_diff_label_changes_only_label_fields_that_changed():
    before = {"coverage": "Cover 3", "down": 3, "run_concept": "Inside Zone"}
    after = {"coverage": "Cover 2", "down": 4, "run_concept": "Inside Zone"}
    changes = ll.diff_label_changes(before, after)
    fields = {c[0] for c in changes}
    assert fields == {"coverage"}          # down is a fact (excluded); run_concept unchanged
    assert changes[0] == ("coverage", "Cover 3", "Cover 2", "reclass")


def test_diff_includes_extra_data_label_fields():
    before = {"shot_zone": "Corner 3"}
    after = {"shot_zone": "Wing 3"}
    changes = ll.diff_label_changes(before, after)
    assert changes == [("shot_zone", "Corner 3", "Wing 3", "reclass")]


# ── adjustment proposal ──────────────────────────────────────────────────────
def _corr(o, n):
    return {"old_value": o, "new_value": n}


def test_propose_needs_minimum_corrections():
    corr = [_corr("Cover 3", "Cover 3 Cloud")] * 5   # below the 10-correction floor
    assert ll.propose_adjustment(corr) is None


def test_propose_dominant_systematic_mapping():
    # 8 of 11 corrections are the same AI mislabel fixed the same way -> propose it.
    corr = [_corr("Cover 3", "Cover 3 Cloud")] * 8 + [
        _corr("Cover 2", "Cover 4"), _corr("Man", "Cover 1"), _corr("Cover 6", "Cover 4")]
    p = ll.propose_adjustment(corr)
    assert p and p["dominant"] is True
    assert p["from_value"] == "Cover 3" and p["to_value"] == "Cover 3 Cloud"
    assert p["support_count"] == 8


def test_propose_contradiction_is_not_dominant():
    # Same 'from' scattered to many 'to's, no winner reaching strong support.
    corr = ([_corr("Cover 3", "Cover 2")] * 3 + [_corr("Cover 3", "Cover 4")] * 3
            + [_corr("Cover 3", "Man")] * 4)
    p = ll.propose_adjustment(corr)
    assert p is not None and p["dominant"] is False
    assert p["contradiction"] is True


# ── apply ────────────────────────────────────────────────────────────────────
def test_apply_relabels_first_class_and_extra_data_fields():
    events = [
        SimpleNamespace(coverage="Cover 3", extra_data={"shot_zone": "Corner 3"}),
        SimpleNamespace(coverage="cover 3", extra_data={}),   # normalized match
        SimpleNamespace(coverage="Cover 2", extra_data={}),   # no match
    ]
    adjustments = [
        {"field": "coverage", "from_value": "Cover 3", "to_value": "Cover 3 Cloud"},
        {"field": "shot_zone", "from_value": "Corner 3", "to_value": "Wing 3"},
    ]
    changed = ll.apply_adjustments(events, adjustments)
    assert changed == 3                                   # 2 coverage + 1 shot_zone
    assert events[0].coverage == "Cover 3 Cloud"
    assert events[0].extra_data["shot_zone"] == "Wing 3"
    assert events[1].coverage == "Cover 3 Cloud"
    assert events[2].coverage == "Cover 2"               # untouched


def test_apply_noop_when_no_adjustments():
    events = [SimpleNamespace(coverage="Cover 3", extra_data={})]
    assert ll.apply_adjustments(events, []) == 0
    assert events[0].coverage == "Cover 3"


# ── async write path (DB stub) ───────────────────────────────────────────────
class _Scalars:
    def __init__(self, items): self._items = items
    def all(self): return self._items


class _Result:
    def __init__(self, items): self._items = items
    def scalars(self): return _Scalars(self._items)
    def scalar_one_or_none(self): return self._items[0] if self._items else None


class _FakeDB:
    def __init__(self, results):
        self._q = list(results)
        self.added = []
        self.commits = 0
    async def execute(self, *_a, **_k):
        return self._q.pop(0) if self._q else _Result([])
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def rollback(self): pass


def _added_types(db):
    return [type(o).__name__ for o in db.added]


def test_record_corrections_writes_row_scores_and_proposes(monkeypatch):
    from backend.models.learning import LabelQualityScore
    event = SimpleNamespace(id="e1", game_id="g1", play_type="pass",
                            event_type="play", extra_data={"auto_detected": True, "confidence": 0.7})
    # A dominant correction history for coverage so recompute proposes an adjustment.
    corr_rows = [SimpleNamespace(old_value="Cover 3", new_value="Cover 3 Cloud")] * 8 + [
        SimpleNamespace(old_value="Cover 2", new_value="Cover 4")] * 3
    db = _FakeDB([
        _Result([]),               # score select in record_corrections -> none (created)
        _Result(corr_rows),        # recompute: corrections
        _Result([]),               # recompute: existing adjustment -> none
        _Result([LabelQualityScore(organization_id="o1")]),  # recompute: score for systematic++
    ])
    n = asyncio.run(ll.record_corrections(
        db, organization_id="o1", user_id="u1", event=event, sport="football",
        changes=[("coverage", "Cover 3", "Cover 3 Cloud", "reclass")], manual_mode=False,
    ))
    assert n == 1
    types = _added_types(db)
    assert "CoachLabelCorrection" in types
    assert "LabelQualityScore" in types
    assert "AccountLearningAdjustment" in types      # dominant history -> proposal created


def test_manual_mode_records_but_does_not_propose():
    event = SimpleNamespace(id="e1", game_id="g1", play_type="pass",
                            event_type="play", extra_data={"auto_detected": True, "confidence": 0.7})
    db = _FakeDB([_Result([])])   # only the score select; recompute must NOT run
    asyncio.run(ll.record_corrections(
        db, organization_id="o1", user_id="u1", event=event, sport="football",
        changes=[("coverage", "Cover 3", "Cover 3 Cloud", "reclass")], manual_mode=True,
    ))
    assert "AccountLearningAdjustment" not in _added_types(db)   # no proposal in manual mode


def test_coach_origin_change_does_not_propose():
    # was_auto_detected False -> a coach refining their own tag, not correcting the AI.
    event = SimpleNamespace(id="e1", game_id="g1", play_type="pass",
                            event_type="play", extra_data={})   # no auto_detected
    db = _FakeDB([_Result([])])
    asyncio.run(ll.record_corrections(
        db, organization_id="o1", user_id="u1", event=event, sport="football",
        changes=[("coverage", "Cover 3", "Cover 3 Cloud", "reclass")], manual_mode=False,
    ))
    assert "AccountLearningAdjustment" not in _added_types(db)


# ── router: ownership + state transitions ────────────────────────────────────
def _adj(**kw):
    base = dict(id="a1", organization_id="o1", sport="football", field="coverage",
                from_value="Cover 3", to_value="Cover 3 Cloud", support_count=8,
                status="pending", note="", activated_by=None,
                updated_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _user(): return SimpleNamespace(id="u1", organization_id="o1")
def _org(): return SimpleNamespace(id="o1", learning_loop_manual=False)


class _RouterDB:
    def __init__(self, adj): self._adj = adj; self.commits = 0
    async def execute(self, *_a, **_k): return _Result([self._adj] if self._adj else [])
    async def commit(self): self.commits += 1


def test_accept_activates():
    a = _adj()
    out = asyncio.run(accept_adjustment("a1", user=_user(), org=_org(), db=_RouterDB(a)))
    assert a.status == "active" and a.activated_by == "u1"
    assert out["adjustment"]["status"] == "active"


def test_reject_and_reset():
    a = _adj(status="active")
    asyncio.run(reject_adjustment("a1", user=_user(), org=_org(), db=_RouterDB(a)))
    assert a.status == "rejected"
    asyncio.run(reset_adjustment("a1", user=_user(), org=_org(), db=_RouterDB(a)))
    assert a.status == "pending" and a.activated_by is None


def test_accept_foreign_adjustment_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(accept_adjustment("a1", user=_user(), org=_org(), db=_RouterDB(None)))
    assert exc.value.status_code == 404


def test_manual_mode_toggle():
    class _UpdDB:
        def __init__(self): self.commits = 0
        async def execute(self, *_a, **_k): return _Result([])
        async def commit(self): self.commits += 1
    out = asyncio.run(set_manual_mode(ManualMode(enabled=True), user=_user(), org=_org(), db=_UpdDB()))
    assert out["manual_mode"] is True
