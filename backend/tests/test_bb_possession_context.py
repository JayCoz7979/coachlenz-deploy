"""
Tests for the flag-gated basketball possession-context + review layer.

Pure, offline, deterministic. The possession/review/dedup pieces need no deps
(stdlib only). One test imports the shipped AiDetectWorker to DOCUMENT that the
time-only dedup merges distinct sub-3s actions while the action-aware dedup keeps
them (item 4: current code fails, flagged-path fix passes). All fixtures are
synthetic and labeled as such; none is real recall evidence.

Run:  python -m backend.tests.test_bb_possession_context
"""
import os

from backend.services.tendency_engine.possession_context import (
    possession_context_enabled,
    maybe_build_possession_context,
    build_possession_context,
    build_review_queue,
    plan_review_pass,
    run_review_pass,
    dedup_basketball_actions,
    ESCALATION_THRESHOLD,
)
from backend.tests.bb_fixtures import POSSESSION_EVENTS, RAW_DETECTIONS

passed, failed = 0, 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {label}")
    else:
        failed += 1; print(f"  FAIL  {label}")


# ── flag gate (default OFF) ───────────────────────────────────────────────────
def test_flag_defaults_off():
    os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)
    assert possession_context_enabled() is False
    assert maybe_build_possession_context(POSSESSION_EVENTS) is None


def test_flag_on_returns_context():
    os.environ["BB_POSSESSION_CONTEXT_ENABLED"] = "true"
    try:
        ctx = maybe_build_possession_context(POSSESSION_EVENTS)
        assert ctx is not None and ctx["deterministic"] is True
    finally:
        os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)


def test_flag_on_blob_includes_review_candidates():
    # The wired blob carries BOTH the possession reconstruction and the review
    # queue, so the coach-facing screen has everything from one payload.
    os.environ["BB_POSSESSION_CONTEXT_ENABLED"] = "true"
    try:
        ctx = maybe_build_possession_context(POSSESSION_EVENTS)
        assert "review_candidates" in ctx
        assert ctx["review_candidates"] == build_review_queue(POSSESSION_EVENTS)
        assert len(ctx["review_candidates"]) == 1          # the 0.60 turnover only
        assert ctx["review_candidates"][0]["status"] == "pending_review"
    finally:
        os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)


def test_flag_on_empty_events_is_safe():
    # ON with no events -> a well-formed empty blob, no crash, nothing invented.
    os.environ["BB_POSSESSION_CONTEXT_ENABLED"] = "true"
    try:
        ctx = maybe_build_possession_context([])
        assert ctx["deterministic"] is True
        assert ctx["possessions"] == []
        assert ctx["summary"]["total_possessions"] == 0
        assert ctx["review_candidates"] == []
    finally:
        os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)


# ── 1. possession reconstruction ──────────────────────────────────────────────
def test_possession_counts_and_teams():
    ctx = build_possession_context(POSSESSION_EVENTS)
    s = ctx["summary"]
    assert s["total_possessions"] == 6, s
    assert s["scouted"] == 5 and s["opponent"] == 1, s


def test_undetected_gaps_flagged_not_invented():
    ctx = build_possession_context(POSSESSION_EVENTS)
    # Three scouted possessions follow a possession-ender with no detected opponent
    # possession between them -> three gaps, flagged, never invented.
    assert ctx["summary"]["undetected_possession_gaps"] == 3, ctx["summary"]
    gapped = [p for p in ctx["possessions"] if p["undetected_possession_gap_before"]]
    assert len(gapped) == 3
    # The opponent possessions themselves are NOT fabricated.
    assert ctx["summary"]["opponent"] == 1


def test_quarters_only_where_tagged():
    ctx = build_possession_context(POSSESSION_EVENTS)
    assert ctx["summary"]["quarters_detected"] == [1, 2], ctx["summary"]


def test_low_confidence_possession_flagged():
    ctx = build_possession_context(POSSESSION_EVENTS)
    low = [p for p in ctx["possessions"] if p["low_confidence"]]
    assert len(low) == 1, low                       # the turnover possession (conf 0.60)
    assert low[0]["ending"] == "turnover"


def test_ending_labels_are_detected_only():
    ctx = build_possession_context(POSSESSION_EVENTS)
    endings = {p["ending"] for p in ctx["possessions"]}
    assert endings <= {"made_shot", "turnover", "steal", "unknown"}, endings


def test_nothing_synthesized_event_counts_match():
    ctx = build_possession_context(POSSESSION_EVENTS)
    total_events = sum(p["event_count"] for p in ctx["possessions"])
    assert total_events == len(POSSESSION_EVENTS)    # every output event is a real input event


# ── 2. review queue ───────────────────────────────────────────────────────────
def test_review_queue_surfaces_only_uncertain():
    q = build_review_queue(POSSESSION_EVENTS)
    assert len(q) == 1, q                            # only the 0.60 turnover
    assert q[0]["status"] == "pending_review"
    assert q[0]["confidence"] < ESCALATION_THRESHOLD


def test_review_queue_never_confirms():
    q = build_review_queue(POSSESSION_EVENTS)
    assert all(c["status"] != "confirmed" for c in q)


# ── 3. review-pass PATH (no spend, no auto-run) ───────────────────────────────
def test_plan_review_pass_is_planning_only():
    q = build_review_queue(POSSESSION_EVENTS)
    plan = plan_review_pass(q)
    assert plan["status"] == "planned_not_executed"
    assert plan["will_spend"] is False
    assert plan["budget_cap"] is None                # no invented dollar threshold
    assert plan["planned_calls"] == len(plan["segments"])


def test_plan_review_pass_budget_cap_passthrough():
    plan = plan_review_pass(build_review_queue(POSSESSION_EVENTS), config={"budget_cap": 2})
    assert plan["budget_cap"] == 2                   # placeholder passthrough only
    assert plan["will_spend"] is False


def test_run_review_pass_without_executor_spends_nothing():
    plan = plan_review_pass(build_review_queue(POSSESSION_EVENTS))
    out = run_review_pass(plan)                      # no executor
    assert out["status"] == "not_executed"
    assert out["spent"] == 0 and out["results"] == []


def test_run_review_pass_injected_executor_makes_no_provider_call():
    plan = plan_review_pass(build_review_queue(POSSESSION_EVENTS))
    calls = []
    out = run_review_pass(plan, executor=lambda seg: calls.append(seg) or "looked")
    assert out["spent"] == 0
    assert len(out["results"]) == len(plan["segments"])


# ── 4. action-aware dedup vs shipped time-only dedup ──────────────────────────
def test_action_aware_keeps_distinct_putback_within_3s():
    out = dedup_basketball_actions([dict(p) for p in RAW_DETECTIONS])
    # 5 raw -> merge the 58/59.4 duplicate, keep everything else = 4
    assert len(out) == 4, [(p["time_seconds"], p["result"]) for p in out]
    # the made putback at 24.0 survives (distinct from the 22.0 miss)
    assert any(p["time_seconds"] == 24.0 and p["result"] == "made" for p in out)
    assert any(p["time_seconds"] == 22.0 and p["result"] == "missed" for p in out)


def test_action_aware_merges_true_duplicate_keeping_higher_confidence():
    out = dedup_basketball_actions([dict(p) for p in RAW_DETECTIONS])
    dupes = [p for p in out if p["time_seconds"] in (58.0, 59.4)]
    assert len(dupes) == 1                           # the two observations of #10's make merged
    assert dupes[0]["confidence"] == 0.90            # kept the higher-confidence read


def test_shipped_time_only_dedup_drops_the_distinct_putback():
    # Documents item 4: the shipped time-only dedup CANNOT tell the putback apart.
    from backend.workers.worker_ai_detect import AiDetectWorker
    w = AiDetectWorker()
    out = w._deduplicate_plays([dict(p) for p in RAW_DETECTIONS], sport="basketball")
    # It merges 22/24 (within 3s) -> the distinct made putback at 24.0 is gone.
    assert not any(p["time_seconds"] == 24.0 for p in out)
    assert len(out) < len(dedup_basketball_actions([dict(p) for p in RAW_DETECTIONS]))


# ── 5. worker wiring: _dedupe_for_sport honors the flag (basketball only) ─────
def test_wiring_flag_off_basketball_uses_time_only():
    # Default off -> the worker's dispatch returns the shipped time-only result,
    # so the distinct putback is dropped (shipped behavior is unchanged).
    os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)
    from backend.workers.worker_ai_detect import AiDetectWorker
    w = AiDetectWorker()
    out = w._dedupe_for_sport([dict(p) for p in RAW_DETECTIONS], "basketball")
    time_only = w._deduplicate_plays([dict(p) for p in RAW_DETECTIONS], "basketball")
    assert [p["time_seconds"] for p in out] == [p["time_seconds"] for p in time_only]
    assert not any(p["time_seconds"] == 24.0 for p in out)


def test_wiring_flag_on_basketball_uses_action_aware():
    # Flag on -> the worker dispatches to the action-aware dedup, so the distinct
    # made putback at 24.0 survives.
    os.environ["BB_POSSESSION_CONTEXT_ENABLED"] = "true"
    try:
        from backend.workers.worker_ai_detect import AiDetectWorker
        w = AiDetectWorker()
        out = w._dedupe_for_sport([dict(p) for p in RAW_DETECTIONS], "basketball")
        assert any(p["time_seconds"] == 24.0 and p["result"] == "made" for p in out)
        assert len(out) == len(dedup_basketball_actions([dict(p) for p in RAW_DETECTIONS]))
    finally:
        os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)


def test_wiring_flag_on_football_stays_time_only():
    # The flag is basketball-only. Football never takes the action-aware path,
    # even with the flag on, so football dedup is identical regardless of the flag.
    os.environ["BB_POSSESSION_CONTEXT_ENABLED"] = "true"
    try:
        from backend.workers.worker_ai_detect import AiDetectWorker
        w = AiDetectWorker()
        fb = [
            {"time_seconds": 10.0, "event_type": "run", "side": "offense", "confidence": 0.9},
            {"time_seconds": 12.0, "event_type": "run", "side": "offense", "confidence": 0.8},
        ]
        out = w._dedupe_for_sport([dict(p) for p in fb], "football")
        time_only = w._deduplicate_plays([dict(p) for p in fb], "football")
        assert [p["time_seconds"] for p in out] == [p["time_seconds"] for p in time_only]
    finally:
        os.environ.pop("BB_POSSESSION_CONTEXT_ENABLED", None)


# ── accessor works on ORM-like objects too ────────────────────────────────────
class _StubEvent:
    def __init__(self, **kw):
        self.extra_data = kw.pop("extra_data", {})
        for k, v in kw.items():
            setattr(self, k, v)


def test_works_on_event_objects():
    evs = [
        _StubEvent(time_seconds=5.0, event_type="shot", side="offense", result="made",
                   extra_data={"confidence": 0.9, "quarter": 1}),
        _StubEvent(time_seconds=25.0, event_type="shot", side="defense", result="made",
                   extra_data={"confidence": 0.9, "quarter": 1}),
    ]
    ctx = build_possession_context(evs)
    assert ctx["summary"]["total_possessions"] == 2
    assert ctx["summary"]["scouted"] == 1 and ctx["summary"]["opponent"] == 1


def test_fixture_is_labeled_synthetic():
    import backend.tests.bb_fixtures as fx
    assert "FIXTURE, NOT REAL RECALL EVIDENCE" in (fx.__doc__ or "")
    assert len(RAW_DETECTIONS) == 5 and len(POSSESSION_EVENTS) == 8


_TESTS = [
    test_flag_defaults_off,
    test_flag_on_returns_context,
    test_flag_on_blob_includes_review_candidates,
    test_flag_on_empty_events_is_safe,
    test_possession_counts_and_teams,
    test_undetected_gaps_flagged_not_invented,
    test_quarters_only_where_tagged,
    test_low_confidence_possession_flagged,
    test_ending_labels_are_detected_only,
    test_nothing_synthesized_event_counts_match,
    test_review_queue_surfaces_only_uncertain,
    test_review_queue_never_confirms,
    test_plan_review_pass_is_planning_only,
    test_plan_review_pass_budget_cap_passthrough,
    test_run_review_pass_without_executor_spends_nothing,
    test_run_review_pass_injected_executor_makes_no_provider_call,
    test_action_aware_keeps_distinct_putback_within_3s,
    test_action_aware_merges_true_duplicate_keeping_higher_confidence,
    test_shipped_time_only_dedup_drops_the_distinct_putback,
    test_wiring_flag_off_basketball_uses_time_only,
    test_wiring_flag_on_basketball_uses_action_aware,
    test_wiring_flag_on_football_stays_time_only,
    test_works_on_event_objects,
    test_fixture_is_labeled_synthetic,
]


def run():
    for t in _TESTS:
        try:
            t()
            check(t.__name__, True)
        except AssertionError as e:
            check(f"{t.__name__}  ->  {e}", False)
        except Exception as e:  # import/other failures are real failures here
            check(f"{t.__name__}  ->  {type(e).__name__}: {e}", False)
    print(f"\n{'='*50}\n  {passed} passed, {failed} failed\n{'='*50}")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
