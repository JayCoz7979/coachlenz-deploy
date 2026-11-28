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


# ── halftime scope (the Halftime Sheet button sends scope="halftime") ────────
from backend.routers.live_game import VALID_SCOPES, ReportRequest  # noqa: E402


def test_halftime_is_a_valid_scope():
    assert "halftime" in VALID_SCOPES
    assert ReportRequest(session_id=GAME, scope="halftime").scope == "halftime"


def test_scope_halftime_football_is_first_two_quarters_whatever_the_period():
    for period in (1, 2, 3, 4, 5, None):
        flt, label = _scope_filter("football", "halftime", period)
        assert flt == {"max_quarter": 2} and label == "Halftime"


def test_scope_halftime_flag_football_matches_football():
    assert _scope_filter("flag_football", "halftime", 2) == ({"max_quarter": 2}, "Halftime")


def test_scope_halftime_basketball_is_first_half():
    flt, label = _scope_filter("basketball", "halftime", 2)
    assert flt == {"max_half": 1} and label == "Halftime"


def test_halftime_filter_applied_to_logged_plays_drops_second_half():
    evs = [_ev(quarter=1), _ev(quarter=2), _ev(quarter=3), _ev(quarter=4)]
    flt, _ = _scope_filter("football", "halftime", 3)
    assert [e.extra_data["quarter"] for e in _apply_event_filter(evs, flt)] == [1, 2]


# ── unit isolation: a play never carries another unit's fields ───────────────
def test_special_teams_play_drops_leaked_opponent_fields():
    # Regression: the previous defensive play's opp_formation / opp_play_type rode
    # along on a Special Teams play and rendered as "Run · Returned".
    p = PlayEntry(possession="us", side="special_teams", st_unit="Kickoff Return",
                  st_result="Returned", result="Returned", returner_jersey="5",
                  opp_formation="Shotgun", opp_play_type="Run", opp_run_gap="left_a",
                  run_gap="right_b", route="Slant")
    e = _play_to_event(ORG, GAME, p)
    assert e.side == "special_teams"
    x = e.extra_data
    assert x["st_unit"] == "Kickoff Return" and x["st_result"] == "Returned"
    assert x["returner_jersey"] == "5"
    for leaked in ("opp_formation", "opp_play_type", "opp_run_gap", "run_gap", "route"):
        assert leaked not in x, leaked


def test_offense_play_drops_opponent_and_special_teams_fields():
    p = PlayEntry(possession="us", play_type="Run", run_gap="left_a",
                  opp_play_type="Pass", opp_formation="Spread", st_unit="Punt")
    x = _play_to_event(ORG, GAME, p).extra_data
    assert x["run_gap"] == "left_a"
    assert not {"opp_play_type", "opp_formation", "st_unit"} & set(x)


def test_defense_play_keeps_opponent_detail_and_drops_our_offense_fields():
    p = PlayEntry(possession="them", opp_play_type="Run", opp_formation="Power-I",
                  opp_run_gap="right_c", run_gap="left_a", ball_carrier_jersey="22",
                  st_result="Returned")
    x = _play_to_event(ORG, GAME, p).extra_data
    assert x["opp_play_type"] == "Run" and x["opp_formation"] == "Power-I"
    assert x["opp_run_gap"] == "right_c"
    assert not {"run_gap", "ball_carrier_jersey", "st_result"} & set(x)


def test_basketball_defense_keeps_opponent_detail():
    p = PlayEntry(possession="them", half=1, opp_shooter="3", opp_primary_action="Drive",
                  shot_zone_allowed="paint", defensive_set="Man", result="Gave Up 2",
                  score_us=10, score_them=12)
    x = _play_to_event(ORG, GAME, p).extra_data
    assert x["opp_shooter"] == "3" and x["shot_zone_allowed"] == "paint"
    assert x["score_us"] == 10 and x["score_them"] == 12


# ── reload: opponent plays keep their detail (no "play · null yd") ───────────
def test_reloaded_defense_play_exposes_opp_play_type_and_null_yards():
    # The defense play's type lives in extra.opp_play_type (the play_type column is
    # empty) and yards may be unset. The API must hand both back so the Play Log can
    # show "Run" instead of "play", and must send yards as null (not a string), which
    # the UI now skips instead of printing "null yd".
    p = PlayEntry(possession="them", opp_play_type="Run", opp_formation="Shotgun", result="Stop at Line")
    e = _play_to_event(ORG, GAME, p)
    e.id = GAME
    view = _event_to_play(e)
    assert view["play_type"] is None
    assert view["yards_gained"] is None
    assert view["extra"]["opp_play_type"] == "Run"
    assert view["extra"]["opp_formation"] == "Shotgun"


def test_score_rides_on_each_play_for_the_momentum_section():
    p = PlayEntry(possession="us", play_type="Run", result="Touchdown", score_us=6, score_them=0)
    x = _play_to_event(ORG, GAME, p).extra_data
    assert x["score_us"] == 6 and x["score_them"] == 0


def test_defense_drive_outcome_is_persisted():
    # opp_outcome ("Touchdown Allowed", "Forced Punt") used to be dropped on save, so
    # it vanished on reload and could not feed the score.
    p = PlayEntry(possession="them", opp_play_type="Pass", opp_outcome="Touchdown Allowed")
    assert _play_to_event(ORG, GAME, p).extra_data["opp_outcome"] == "Touchdown Allowed"
