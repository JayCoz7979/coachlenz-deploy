"""
Inactive-coach detection (pure, no DB). Activity = the later of last_login_at and
the coach's most recent analysis run; stale-past-`days` (or never active) flags them.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.inactivity import (
    clamp_days,
    compute_inactive_coaches,
    last_active_at,
    DEFAULT_INACTIVE_DAYS,
)

NOW = datetime(2026, 7, 30, 12, 0, 0)


def _user(uid, name="Coach", login=None, role="coach", email="c@x.io"):
    return SimpleNamespace(id=uid, name=name, email=email, role=role, last_login_at=login)


def _run(uid, created_at):
    return SimpleNamespace(user_id=uid, created_at=created_at)


def test_clamp_days_bounds_and_default():
    assert clamp_days(14) == 14
    assert clamp_days(None) == DEFAULT_INACTIVE_DAYS
    assert clamp_days(0) == 1
    assert clamp_days(9999) == 365


def test_recent_login_is_active():
    users = [_user("u1", login=NOW - timedelta(days=3))]
    out = compute_inactive_coaches(users, [], NOW, days=14)
    assert out == []


def test_stale_login_is_flagged_with_day_count():
    users = [_user("u1", name="Stale", login=NOW - timedelta(days=40))]
    out = compute_inactive_coaches(users, [], NOW, days=14)
    assert len(out) == 1
    assert out[0]["name"] == "Stale"
    assert out[0]["days_inactive"] == 40
    assert out[0]["never_active"] is False


def test_recent_analysis_run_keeps_coach_active_despite_old_login():
    # Old login, but they ran an analysis 2 days ago → active.
    users = [_user("u1", login=NOW - timedelta(days=60))]
    runs = [_run("u1", NOW - timedelta(days=2))]
    out = compute_inactive_coaches(users, runs, NOW, days=14)
    assert out == []


def test_never_active_seat_is_flagged():
    users = [_user("u1", name="NeverUsed", login=None)]
    out = compute_inactive_coaches(users, [], NOW, days=14)
    assert len(out) == 1
    assert out[0]["never_active"] is True
    assert out[0]["days_inactive"] is None
    assert out[0]["last_active_at"] is None


def test_viewer_is_excluded():
    users = [_user("ad", login=None), _user("u1", login=NOW - timedelta(days=90))]
    out = compute_inactive_coaches(users, [], NOW, days=14, exclude_user_id="ad")
    assert [c["user_id"] for c in out] == ["u1"]


def test_sort_never_active_first_then_longest_inactive():
    users = [
        _user("a", name="Lapsed20", login=NOW - timedelta(days=20)),
        _user("b", name="Never", login=None),
        _user("c", name="Lapsed50", login=NOW - timedelta(days=50)),
    ]
    out = compute_inactive_coaches(users, [], NOW, days=14)
    assert [c["name"] for c in out] == ["Never", "Lapsed50", "Lapsed20"]


def test_timezone_aware_timestamps_do_not_crash():
    aware = datetime(2026, 7, 1, tzinfo=timezone.utc)  # aware, ~29 days before NOW
    users = [_user("u1", login=aware)]
    runs = [_run("u1", datetime(2026, 6, 1, tzinfo=timezone.utc))]
    out = compute_inactive_coaches(users, runs, NOW, days=14)
    assert len(out) == 1 and out[0]["days_inactive"] == 29


def test_last_active_at_picks_the_later_signal():
    u = _user("u1", login=NOW - timedelta(days=10))
    la = last_active_at(u, NOW - timedelta(days=2))  # a more recent run
    assert la == NOW - timedelta(days=2)
