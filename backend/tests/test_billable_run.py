"""Finding #4: dry_run and test detections deliver no analysis, so they must not
record an AnalysisUsage row (which counts against the coach's monthly credit)."""
from backend.routers.ai_detect import _is_billable_run


def test_real_runs_are_billable():
    assert _is_billable_run(dry_run=False, test=False) is True


def test_dry_run_is_not_billable():
    assert _is_billable_run(dry_run=True, test=False) is False


def test_test_run_is_not_billable():
    assert _is_billable_run(dry_run=False, test=True) is False


def test_usage_insert_is_gated_by_billable_check():
    # Structural guard: the AnalysisUsage insert must sit behind the billable gate
    # so a refactor can't reintroduce the charge for previews.
    import inspect
    import backend.routers.ai_detect as ai

    src = inspect.getsource(ai.trigger_auto_detect)
    gate = src.find("if _is_billable_run(dry_run, test):\n        db.add(AnalysisUsage(")
    assert gate != -1, "AnalysisUsage insert must be guarded by _is_billable_run"
