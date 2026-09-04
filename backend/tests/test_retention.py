"""
Retention telemetry (pure, no DB). Cohort = ISO signup week; activation = a first
analysis within 7 days; return = a second analysis within 30 days. In-window
cohorts are 'maturing' and never trip the stop line.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services import retention as R

# Far enough in the past that every cohort below is fully matured by NOW.
NOW = datetime(2026, 9, 1, 12, 0, 0)


def _org(oid, signup):
    return SimpleNamespace(id=oid, created_at=signup)


def _run(oid, at):
    return SimpleNamespace(organization_id=oid, created_at=at)


def test_iso_cohort_is_signup_week():
    assert R.iso_cohort(datetime(2026, 9, 1)) == R.iso_cohort(datetime(2026, 9, 2))
    assert R.iso_cohort(datetime(2026, 1, 5)) == "2026-W02"


def test_gate_status_thresholds():
    assert R.gate_status(0.40, True) == "pass"
    assert R.gate_status(0.55, True) == "pass"
    assert R.gate_status(0.30, True) == "watch"
    assert R.gate_status(0.20, True) == "watch"        # stop line is strict <20%
    assert R.gate_status(0.19, True) == "stop"
    assert R.gate_status(0.0, True) == "stop"
    assert R.gate_status(0.0, False) == "maturing"     # window still open
    assert R.gate_status(None, True) == "maturing"


def test_activation_counts_first_analysis_within_7_days():
    signup = datetime(2026, 1, 1)
    orgs = [_org("a", signup), _org("b", signup), _org("c", signup)]
    runs = [
        _run("a", signup + timedelta(days=2)),    # activated
        _run("b", signup + timedelta(days=7)),    # activated (boundary inclusive)
        _run("c", signup + timedelta(days=8)),    # too late -> not activated
    ]
    out = R.build_cohorts(orgs, runs, now=NOW)
    coh = out["cohorts"][0]
    assert coh["size"] == 3
    assert coh["activated"] == 2
    assert coh["activation_rate"] == round(2 / 3, 4)


def test_return_needs_second_analysis_within_30_days():
    signup = datetime(2026, 1, 1)
    orgs = [_org("a", signup), _org("b", signup), _org("c", signup), _org("d", signup)]
    runs = [
        # a: two analyses, second on day 10 -> returned
        _run("a", signup + timedelta(days=1)), _run("a", signup + timedelta(days=10)),
        # b: two analyses, second on day 31 -> NOT returned
        _run("b", signup + timedelta(days=1)), _run("b", signup + timedelta(days=31)),
        # c: only one analysis -> activated but NOT returned
        _run("c", signup + timedelta(days=1)),
        # d: no analyses at all
    ]
    out = R.build_cohorts(orgs, runs, now=NOW)
    coh = out["cohorts"][0]
    assert coh["returned"] == 1
    assert coh["return_rate"] == round(1 / 4, 4)
    # Gate at 25% return sits between stop (20%) and bar (40%) -> watch.
    assert coh["gate"] == "watch"


def test_second_of_three_within_window_counts_even_if_third_is_late():
    signup = datetime(2026, 1, 1)
    orgs = [_org("a", signup)]
    runs = [
        _run("a", signup + timedelta(days=2)),
        _run("a", signup + timedelta(days=5)),    # second -> within 30d -> returned
        _run("a", signup + timedelta(days=90)),   # third, irrelevant
    ]
    out = R.build_cohorts(orgs, runs, now=NOW)
    assert out["cohorts"][0]["returned"] == 1


def test_immature_cohort_never_trips_stop_line():
    recent = NOW - timedelta(days=5)              # return window still open
    orgs = [_org("a", recent), _org("b", recent)]
    runs = [_run("a", recent + timedelta(hours=1))]  # one activation, no returns yet
    out = R.build_cohorts(orgs, runs, now=NOW)
    coh = out["cohorts"][0]
    assert coh["matured"] is False
    assert coh["gate"] == "maturing"
    # Summary rolls up matured cohorts only, so this cohort is excluded there.
    assert out["summary"]["matured_orgs"] == 0
    assert out["summary"]["gate"] == "maturing"


def test_summary_rolls_up_only_matured_cohorts_and_verdicts_pass():
    old = datetime(2026, 1, 1)
    orgs = [_org(f"o{i}", old) for i in range(5)]
    # 2 of 5 return -> 40% -> pass.
    runs = []
    for i in range(2):
        runs += [_run(f"o{i}", old + timedelta(days=1)), _run(f"o{i}", old + timedelta(days=5))]
    for i in range(2, 5):
        runs.append(_run(f"o{i}", old + timedelta(days=1)))  # activated only
    out = R.build_cohorts(orgs, runs, now=NOW)
    s = out["summary"]
    assert s["matured_orgs"] == 5
    assert s["return_rate"] == 0.40
    assert s["gate"] == "pass"
    assert s["return_bar"] == R.RETURN_BAR
    assert s["stop_line"] == R.STOP_LINE


def test_empty_state_is_clean():
    out = R.build_cohorts([], [], now=NOW)
    assert out["cohorts"] == []
    assert out["summary"]["matured_orgs"] == 0
    assert out["summary"]["return_rate"] is None
    assert out["summary"]["gate"] == "maturing"


def test_tz_aware_signups_compare_cleanly():
    from datetime import timezone
    signup = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orgs = [_org("a", signup)]
    runs = [_run("a", signup + timedelta(days=2)), _run("a", signup + timedelta(days=4))]
    out = R.build_cohorts(orgs, runs, now=NOW)   # naive now vs aware rows must not raise
    assert out["cohorts"][0]["returned"] == 1
