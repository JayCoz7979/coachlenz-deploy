"""
Honesty guards for basketball Category 1 (Time of Possession) and Category 5 (Pace)
on single-camera film that carries NO possession clock.

Regression for the DHHS vs LHS report:
  - Category 1 marked every player a "ghost" (0.0 possession seconds) and used that
    to drive a bogus "sag off #2, he just catches and passes" game-plan call.
  - Category 5 reported 0 offensive possessions while the rest of the report counted
    9 (it saw only the defense's possession rows and skipped the offense fallback).

Run:  python -m backend.tests.test_bb_possession_pace
"""
from types import SimpleNamespace
from backend.services.tendency_engine.basketball_scout import (
    _category_1_possession, _category_5_pace, build_scouting_report,
)


def E(event_type, side="offense", result=None, **extra):
    return SimpleNamespace(event_type=event_type, side=side, result=result, extra_data=extra)


def test_category1_withholds_roles_without_a_possession_clock():
    # Shots/turnovers with touches but NO possession_seconds (single-cam reality).
    ev = [
        E("shot", side="offense", primary_player_jersey="2", shot_zone="Restricted Area", quarter=2),
        E("turnover", side="offense", primary_player_jersey="22", quarter=2),
        E("shot", side="offense", primary_player_jersey="2", shot_zone="Left Wing 3", quarter=2),
    ]
    c1 = _category_1_possession(ev)
    assert c1["timing_available"] is False, "no possession seconds -> timing must be unavailable"
    assert c1["ghost_players"] == [], "must not fabricate ghost players from missing timing"
    assert c1["dead_zone_players"] == [], "must not fabricate dead-zone players"
    assert c1["isolation_dependency_flag"] is False, "cannot claim iso dependency without timing"
    assert c1["primary_share_pct"] is None, "no possession-share % when timing is unavailable"
    assert all(r["role"] == "unknown" for r in c1["players"]), "roles are withheld without timing"
    # #2 has the most touches (2) -> named the primary handler by touches.
    assert c1["primary_ball_handler"] == "2"
    assert c1["note"], "must explain why timing is withheld"
    print("  C1: roles/ghost/iso withheld without a clock; handler ranked by touches ✓")


def test_category1_classifies_when_timing_present():
    ev = [E("possession", side="offense", primary_player_jersey="3",
            possession_seconds=9.0, quarter=1) for _ in range(6)]
    ev += [E("possession", side="offense", primary_player_jersey="9",
             possession_seconds=1.5, quarter=1) for _ in range(4)]
    c1 = _category_1_possession(ev)
    assert c1["timing_available"] is True
    assert c1["primary_ball_handler"] == "3"
    assert c1["primary_share_pct"] is not None
    print("  C1: full role classification preserved when a clock exists ✓")


def test_category5_counts_offense_even_when_only_defense_has_possession_rows():
    # Single-cam pattern: explicit DEFENSE possession rows + offense shots/turnovers.
    ev = [
        E("possession", side="defense", quarter=2),
        E("possession", side="defense", quarter=2),
        E("shot", side="offense", primary_player_jersey="2", shot_zone="Restricted Area", quarter=2),
        E("turnover", side="offense", primary_player_jersey="22", quarter=2),
        E("shot", side="offense", primary_player_jersey="2", shot_zone="Left Wing 3", quarter=2),
    ]
    c5 = _category_5_pace(ev)
    assert c5["offensive_possessions"] == 3, f"offense must not read 0, got {c5}"
    assert c5["defensive_possessions"] == 2, f"defense possessions from explicit rows, got {c5}"
    assert c5["timing_available"] is False, "no possession seconds -> pace timing unavailable"
    assert c5["pace_rating"] == "unknown"
    assert c5["note"], "must explain why pace rating is withheld"
    # And it must agree with what build_scouting_report reports up top.
    rep = build_scouting_report(ev)
    assert rep["category_5_pace"]["offensive_possessions"] == 3
    print("  C5: offense counted via fallback; no 0-vs-9 contradiction ✓")


def run():
    test_category1_withholds_roles_without_a_possession_clock()
    test_category1_classifies_when_timing_present()
    test_category5_counts_offense_even_when_only_defense_has_possession_rows()
    print("\nALL POSSESSION/PACE HONESTY ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
