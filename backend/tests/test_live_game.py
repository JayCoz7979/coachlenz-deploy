"""
Unit tests for the Live Game Play Logger pure logic — no DB, no network.

Covers the two pieces that would silently corrupt a report if they drifted:
  1. possession -> Event.side mapping (the tendency engine splits on side)
  2. the halftime event filter in the report worker (first-half scoping)
plus the play <-> event field mapping the logger round-trips through.
"""
import types
import pytest

from backend.routers.live_game import (
    _side_from_possession, _play_to_event, _event_to_play, PlayEntry, _scope_filter,
)
from backend.workers.worker_reports import _apply_event_filter

pytestmark = pytest.mark.unit

ORG = "00000000-0000-0000-0000-000000000001"
GAME = "00000000-0000-0000-0000-000000000002"


# ── side mapping ─────────────────────────────────────────────────────────────
def test_possession_us_is_our_offense():
    assert _side_from_possession("us", None, "Run") == "offense"


def test_possession_them_is_our_defense():
    assert _side_from_possession("them", None, "Pass") == "defense"


def test_special_teams_wins_over_possession():
    assert _side_from_possession("us", None, "special_teams") == "special_teams"


def test_explicit_side_override():
    assert _side_from_possession("us", "special_teams", "Run") == "special_teams"


def test_unknown_possession_defaults_offense():
    assert _side_from_possession(None, None, None) == "offense"


# ── play -> event ────────────────────────────────────────────────────────────
def test_run_play_maps_to_offense_event_with_extra_and_player():
    p = PlayEntry(possession="us", quarter=1, down=1, distance=10, play_type="Run",
                  run_gap="left_a", run_category="Inside Run", ball_carrier_jersey="22",
                  primary_player_jersey="22", yards_gained=6, result="First Down")
    e = _play_to_event(ORG, GAME, p)
    assert e.side == "offense"
    assert e.event_type == "play"
    assert e.down == 1 and e.yards_gained == 6
    assert e.player == "22"                       # -> tendency engine player tendencies
    assert e.extra_data["run_gap"] == "left_a"
    assert e.extra_data["quarter"] == 1
    assert e.extra_data["run_category"] == "Inside Run"


def test_defense_play_maps_to_defense_side():
    p = PlayEntry(possession="them", opp_play_type="Pass", opp_target="11", coverage="Cover 3")
    e = _play_to_event(ORG, GAME, p)
    assert e.side == "defense"
    assert e.coverage == "Cover 3"
    assert e.extra_data["opp_target"] == "11"


def test_defensive_front_maps_to_column_not_extra():
    # Regression: defensive_front must land on the Event COLUMN (which the report's
    # fronts analysis reads), not buried in extra_data where it was silently lost.
    p = PlayEntry(possession="them", defensive_front="4-3", coverage="Cover 3")
    e = _play_to_event(ORG, GAME, p)
    assert e.defensive_front == "4-3"
    assert "defensive_front" not in (e.extra_data or {})


def test_coaching_point_sets_highlight_and_note():
    p = PlayEntry(possession="us", is_coaching_point=True, note="watch the backside")
    e = _play_to_event(ORG, GAME, p)
    assert e.is_highlight is True
    assert e.coach_note == "watch the backside"


def test_client_uid_round_trips_for_idempotent_sync():
    # The offline queue tags each play with a client_uid; it must persist to
    # extra_data and come back on read so a reconnect flush can dedupe on it.
    p = PlayEntry(possession="us", play_type="Run", client_uid="abc-123")
    e = _play_to_event(ORG, GAME, p)
    assert e.extra_data["client_uid"] == "abc-123"
    e.id = GAME
    assert _event_to_play(e)["client_uid"] == "abc-123"


def test_event_to_play_round_trip_exposes_extra():
    p = PlayEntry(possession="us", quarter=2, play_type="Pass", route="Slant",
                  target_jersey="80", primary_player_jersey="80", yards_gained=12)
    e = _play_to_event(ORG, GAME, p)
    # simulate a persisted id the way the API returns it
    e.id = GAME
    view = _event_to_play(e)
    assert view["side"] == "offense"
    assert view["quarter"] == 2
    assert view["player"] == "80"
    assert view["extra"]["route"] == "Slant"


# ── halftime event filter (worker) ───────────────────────────────────────────
def _ev(**extra):
    return types.SimpleNamespace(extra_data=extra)


def test_no_filter_returns_all():
    evs = [_ev(quarter=1), _ev(quarter=3)]
    assert _apply_event_filter(evs, None) == evs
    assert _apply_event_filter(evs, {}) == evs


def test_halftime_max_quarter_drops_second_half():
    evs = [_ev(quarter=1), _ev(quarter=2), _ev(quarter=3), _ev(quarter=4)]
    kept = _apply_event_filter(evs, {"max_quarter": 2})
    assert [e.extra_data["quarter"] for e in kept] == [1, 2]


def test_halftime_max_quarter_drops_overtime():
    evs = [_ev(quarter=2), _ev(quarter=5)]  # OT is 5
    kept = _apply_event_filter(evs, {"max_quarter": 2})
    assert [e.extra_data["quarter"] for e in kept] == [2]


def test_halftime_max_half_basketball():
    evs = [_ev(half=1), _ev(half=2)]
    kept = _apply_event_filter(evs, {"max_half": 1})
    assert [e.extra_data["half"] for e in kept] == [1]


def test_untimed_and_meta_events_are_kept_on_scope():
    # a play with no recorded period must not be silently dropped by a scope pass
    evs = [_ev(quarter=1), _ev(), _ev(quarter=3)]
    kept = _apply_event_filter(evs, {"max_quarter": 2})
    assert len(kept) == 2   # q1 + the untimed one; q3 dropped


def test_this_quarter_range_filter():
    # min==max isolates a single quarter (the adjustment report)
    evs = [_ev(quarter=2), _ev(quarter=3), _ev(quarter=4)]
    kept = _apply_event_filter(evs, {"min_quarter": 3, "max_quarter": 3})
    assert [e.extra_data["quarter"] for e in kept] == [3]


def test_second_half_range_filter():
    evs = [_ev(quarter=1), _ev(quarter=2), _ev(quarter=3), _ev(quarter=4)]
    kept = _apply_event_filter(evs, {"min_quarter": 3, "max_quarter": 4})
    assert [e.extra_data["quarter"] for e in kept] == [3, 4]


def test_min_half_filter_basketball():
    evs = [_ev(half=1), _ev(half=2)]
    kept = _apply_event_filter(evs, {"min_half": 2, "max_half": 2})
    assert [e.extra_data["half"] for e in kept] == [2]


# ── scope -> filter helper ───────────────────────────────────────────────────
def test_scope_full_has_no_filter():
    flt, label = _scope_filter("football", "full", 3)
    assert flt is None and label == "Full Game"


def test_scope_this_quarter_football():
    flt, label = _scope_filter("football", "this_quarter", 3)
    assert flt == {"min_quarter": 3, "max_quarter": 3} and label == "Q3"


def test_scope_this_half_football_second_half():
    flt, label = _scope_filter("football", "this_half", 3)
    assert flt == {"min_quarter": 3, "max_quarter": 4} and label == "2nd Half"


def test_scope_this_half_basketball():
    flt, label = _scope_filter("basketball", "this_half", 2)
    assert flt == {"min_half": 2, "max_half": 2} and label == "Half 2"


def test_scope_overtime_football():
    flt, label = _scope_filter("football", "this_quarter", 5)
    assert flt == {"min_quarter": 5} and label == "Overtime"
