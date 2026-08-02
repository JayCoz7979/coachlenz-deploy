"""
Unit tests for the bespoke Live Game report stats — no DB, no network.

These guard the DETERMINISTIC layer: every number the 9-section report cites is
counted here in Python, so if the counting drifts the report lies. The LLM prose
layer is not tested (it only narrates these numbers).
"""
import types
import asyncio
import pytest

from backend.services.live_game_report import (
    compute_football_stats, compute_basketball_stats, compute_season_baseline,
    generate_live_game_sections, _in_red_zone, _converted, _poss_points, _score_momentum,
)

pytestmark = pytest.mark.unit


def ev(**kw):
    base = dict(event_type="play", side="offense", play_type=None, down=None, distance=None,
                field_position=None, formation=None, result=None, yards_gained=None,
                coverage=None, blitz=None, defensive_front=None, player=None, extra_data={})
    base.update(kw)
    return types.SimpleNamespace(**base)


# ── helpers ──────────────────────────────────────────────────────────────────
def test_red_zone_detection():
    assert _in_red_zone("OPP 15") is True
    assert _in_red_zone("OPP 20") is True
    assert _in_red_zone("OPP 21") is False
    assert _in_red_zone("OWN 15") is False
    assert _in_red_zone(None) is False


def test_converted_by_yards_and_by_result():
    assert _converted(ev(down=3, distance=5, yards_gained=6)) is True
    assert _converted(ev(down=3, distance=5, yards_gained=2)) is False
    assert _converted(ev(down=3, distance=20, yards_gained=1, result="Touchdown")) is True


def test_poss_points_mapping():
    assert _poss_points("3 pts") == 3
    assert _poss_points("2 pts") == 2
    assert _poss_points("1 pt FT") == 1
    assert _poss_points("Missed") == 0


# ── football stats ───────────────────────────────────────────────────────────
def _football_events():
    return [
        ev(side="offense", play_type="Run", down=1, distance=10, yards_gained=6, formation="Shotgun",
           field_position="OWN 40", player="22",
           extra_data={"quarter": 1, "ball_carrier_jersey": "22", "run_gap": "left_a", "run_category": "Inside Run",
                       "score_us": 0, "score_them": 0, "possession": "us"}),
        ev(side="offense", play_type="Run", down=2, distance=4, yards_gained=4, formation="Shotgun",
           field_position="OWN 46", player="22",
           extra_data={"quarter": 1, "ball_carrier_jersey": "22", "run_gap": "left_a",
                       "score_us": 0, "score_them": 0, "possession": "us"}),
        ev(side="offense", play_type="Pass", down=1, distance=10, yards_gained=15, formation="Trips",
           field_position="OPP 15", player="80", result="Touchdown",
           extra_data={"quarter": 2, "target_jersey": "80", "passer_jersey": "7", "route": "Slant",
                       "pass_result": "Completion", "score_us": 7, "score_them": 0, "possession": "us"}),
        ev(side="defense", play_type=None, down=3, distance=8, yards_gained=2, coverage="Cover 3",
           defensive_front="4-3", blitz="Yes",
           extra_data={"quarter": 1, "opp_play_type": "Pass", "opp_target": "11", "opp_route": "Out",
                       "score_us": 0, "score_them": 0, "possession": "them"}),
        ev(side="special_teams",
           extra_data={"quarter": 2, "st_unit": "Punt", "st_result": "Downed", "st_yards": 42, "possession": "us"}),
    ]


def test_football_offense_summary():
    s = compute_football_stats(_football_events(), {})
    off = s["offense"]
    assert off["plays"] == 3
    assert off["total_yards"] == 25
    assert off["run"]["plays"] == 2 and off["run"]["yards"] == 10 and off["run"]["ypc"] == 5.0
    assert off["pass"]["plays"] == 1 and off["pass"]["completions"] == 1
    assert off["red_zone"]["trips_plays"] == 1 and off["red_zone"]["touchdowns"] == 1
    # most productive formation surfaces (Trips = 15 yards)
    assert off["formations"][0]["formation"] == "Trips"


def test_incompletion_not_counted_as_completion():
    # Regression: "incompletion" contains the substring "completion" — the counter
    # must NOT treat an incompletion as a completion.
    evs = [
        ev(side="offense", play_type="Pass", yards_gained=10, player="80",
           extra_data={"quarter": 1, "target_jersey": "80", "passer_jersey": "7", "pass_result": "Completion"}),
        ev(side="offense", play_type="Pass", yards_gained=0, player="80",
           extra_data={"quarter": 1, "target_jersey": "80", "passer_jersey": "7", "pass_result": "Incompletion"}),
    ]
    s = compute_football_stats(evs, {})
    assert s["offense"]["pass"]["plays"] == 2
    assert s["offense"]["pass"]["completions"] == 1        # not 2
    assert s["players_offense"]["targets"][0]["catches"] == 1
    assert s["players_offense"]["passers"][0]["completions"] == 1


def test_football_offense_players_and_unused_roster():
    config = {"our_roster": [{"jersey": "22"}, {"jersey": "80"}, {"jersey": "7"}, {"jersey": "99", "name": "Bench"}]}
    s = compute_football_stats(_football_events(), config)
    po = s["players_offense"]
    assert po["ball_carriers"][0]["jersey"] == "22"
    assert po["ball_carriers"][0]["carries"] == 2 and po["ball_carriers"][0]["yards"] == 10
    assert po["targets"][0]["jersey"] == "80" and po["targets"][0]["catches"] == 1
    assert po["passers"][0]["jersey"] == "7" and po["passers"][0]["completions"] == 1
    # #99 was pre-loaded but never touched the ball -> flagged unused
    assert any(r["jersey"] == "99" for r in po["unused_roster"])


def test_football_defense_and_opponent_players():
    s = compute_football_stats(_football_events(), {})
    d = s["defense"]
    assert d["plays"] == 1 and d["yards_allowed"] == 2
    assert d["pressure"]["blitzes"] == 1
    assert d["third_down_allowed"]["attempts"] == 1 and d["third_down_allowed"]["conversions_allowed"] == 0
    opp = s["players_opponent"]
    assert opp["targets"][0]["jersey"] == "11"
    assert opp["targets"][0]["vs_coverage"].get("Cover 3") == 1


def test_football_special_teams():
    s = compute_football_stats(_football_events(), {})
    st = s["special_teams"]
    assert st["plays"] == 1
    punt = st["by_unit"][0]
    assert punt["unit"] == "Punt" and punt["avg_yards"] == 42.0


# ── basketball stats ─────────────────────────────────────────────────────────
def _basketball_events():
    return [
        ev(side="offense", extra_data={"half": 1, "shooter_jersey": "5", "shot_zone": "wing3_left",
                                       "shot_result": "Made", "possession_result": "3 pts",
                                       "ball_handler_jersey": "3", "score_us": 3, "score_them": 0, "possession": "us"}),
        ev(side="offense", extra_data={"half": 1, "shooter_jersey": "5", "shot_zone": "paint",
                                       "shot_result": "Missed", "possession_result": "Missed",
                                       "score_us": 3, "score_them": 0, "possession": "us"}),
        ev(side="offense", extra_data={"half": 1, "shot_result": "Turnover Before Shot", "turnover_type": "Bad Pass",
                                       "possession_result": "Turnover", "ball_entry": "Transition",
                                       "score_us": 3, "score_them": 0, "possession": "us"}),
        ev(side="defense", extra_data={"half": 1, "opp_shooter": "10", "shot_zone_allowed": "paint",
                                       "fouled_by_jersey": "4", "defensive_set": "Man",
                                       "score_us": 3, "score_them": 2, "possession": "them"}),
        ev(side="defense", extra_data={"half": 1, "fouled_by_jersey": "4",
                                       "score_us": 3, "score_them": 2, "possession": "them"}),
        ev(side="defense", extra_data={"half": 1, "fouled_by_jersey": "4",
                                       "score_us": 3, "score_them": 4, "possession": "them"}),
    ]


def test_basketball_offense_summary():
    s = compute_basketball_stats(_basketball_events(), {})
    off = s["offense"]
    assert off["possessions"] == 3
    assert off["points"] == 3
    assert off["points_per_possession"] == 1.0
    assert off["turnovers"]["count"] == 1 and off["turnovers"]["by_type"].get("Bad Pass") == 1
    # wing3_left 1/1, paint 0/1
    zmap = {z["zone"]: z for z in off["shot_zones"]}
    assert zmap["wing3_left"]["makes"] == 1 and zmap["paint"]["makes"] == 0


def test_basketball_players_and_foul_trouble():
    s = compute_basketball_stats(_basketball_events(), {})
    assert s["players_offense"]["shooters"][0]["jersey"] == "5"
    assert s["players_offense"]["shooters"][0]["attempts"] == 2
    # #4 fouled 3 times -> foul trouble alert
    ft = s["defense"]["foul_trouble"]
    assert ft and ft[0]["jersey"] == "4" and ft[0]["fouls"] == 3
    assert s["players_opponent"]["shooters"][0]["jersey"] == "10"


# ── score/momentum + season gating ───────────────────────────────────────────
def test_score_momentum_by_period():
    m = _score_momentum(_football_events(), "quarter")
    assert m["by_period"]["1"]["us"] == 0
    assert m["by_period"]["2"]["us"] == 7
    assert m["possession_play_counts"]["us"] >= 3


def test_season_baseline_requires_three_games():
    assert compute_season_baseline("football", _football_events(), 2, {}) is None
    base = compute_season_baseline("football", _football_events(), 3, {})
    assert base and base["games"] == 3 and "yards_per_play" in base


def test_generate_short_circuits_without_enough_plays():
    # < 3 plays returns a guidance section and never calls the LLM
    out = asyncio.run(
        generate_live_game_sections("football", [ev(side="offense")], {"scope": "halftime"}, {})
    )
    assert len(out) == 1 and "Not Enough Plays" in out[0]["heading"]
