"""
Conversion funnel telemetry (pure, no DB). Anonymous top steps dedup by anon_id;
signup steps count rows. Gate metric is visitor -> completed signup.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services import funnel as F

NOW = datetime(2026, 9, 4, 12, 0, 0)


def _ev(event, anon_id=None, ts=None):
    return SimpleNamespace(event=event, anon_id=anon_id, created_at=ts or NOW)


def _basic_rows():
    rows = []
    # 10 unique visitors land (one visits twice -> still one).
    for i in range(10):
        rows.append(_ev("landing_view", anon_id=f"v{i}"))
    rows.append(_ev("landing_view", anon_id="v0"))  # refresh, must not inflate
    # 4 click start
    for i in range(4):
        rows.append(_ev("cta_click", anon_id=f"v{i}"))
    # 3 reach signup page
    for i in range(3):
        rows.append(_ev("signup_view", anon_id=f"v{i}"))
    # 2 create an account (server events, one row each)
    rows += [_ev("signup_start"), _ev("signup_start")]
    # 1 completes signup
    rows += [_ev("signup_complete")]
    return rows


def test_step_counts_dedup_visitors():
    out = F.build_funnel(_basic_rows(), now=NOW)
    counts = {s["step"]: s["count"] for s in out["steps"]}
    assert counts["landing_view"] == 10        # refresh did not inflate
    assert counts["cta_click"] == 4
    assert counts["signup_view"] == 3
    assert counts["signup_start"] == 2
    assert counts["signup_complete"] == 1


def test_visitor_to_signup_and_gate():
    out = F.build_funnel(_basic_rows(), now=NOW)
    assert out["visitor_to_signup"] == 0.1     # 1 / 10
    assert out["gate"] == "pass"               # 10% >= 5% bar


def test_gate_stop_and_watch_bands():
    assert F.gate_status(0.05) == "pass"
    assert F.gate_status(0.049) == "watch"
    assert F.gate_status(0.02) == "watch"      # stop line is strict <2%
    assert F.gate_status(0.019) == "stop"
    assert F.gate_status(None) == "no_data"


def test_biggest_drop_is_named_with_a_number():
    out = F.build_funnel(_basic_rows(), now=NOW)
    drop = out["biggest_drop"]
    # 10 -> 4 at landing->cta loses 6, the largest single leak.
    assert drop["from"] == "landing_view" and drop["to"] == "cta_click"
    assert drop["lost"] == 6
    assert drop["drop_rate"] == 0.6


def test_window_excludes_old_events():
    old = NOW - timedelta(days=40)
    rows = [_ev("landing_view", anon_id="a", ts=old),
            _ev("landing_view", anon_id="b", ts=NOW),
            _ev("signup_complete", ts=NOW)]
    out = F.build_funnel(rows, now=NOW, window_days=30)
    counts = {s["step"]: s["count"] for s in out["steps"]}
    assert counts["landing_view"] == 1          # the 40-day-old visit is excluded
    assert out["visitor_to_signup"] == 1.0


def test_empty_state_is_clean():
    out = F.build_funnel([], now=NOW)
    assert all(s["count"] == 0 for s in out["steps"])
    assert out["visitor_to_signup"] is None
    assert out["biggest_drop"] is None
    assert out["gate"] == "no_data"


def test_only_known_client_events_are_writable():
    assert "signup_start" not in F.ALLOWED_CLIENT_EVENTS
    assert "signup_complete" not in F.ALLOWED_CLIENT_EVENTS
    assert F.ALLOWED_CLIENT_EVENTS == {"landing_view", "cta_click", "signup_view"}


def test_tz_aware_events_do_not_raise():
    from datetime import timezone
    rows = [_ev("landing_view", anon_id="a", ts=datetime(2026, 9, 4, tzinfo=timezone.utc)),
            _ev("signup_complete", ts=datetime(2026, 9, 4, tzinfo=timezone.utc))]
    out = F.build_funnel(rows, now=NOW)
    assert out["visitor_to_signup"] == 1.0
