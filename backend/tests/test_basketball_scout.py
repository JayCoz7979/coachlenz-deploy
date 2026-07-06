"""
Synthetic-data test for the six-category basketball scouting engine.

Builds a realistic Tanner-opponent game (one dominant ball-handler, a turnover-prone
guard, an active deflection defender, a perimeter-heavy shooter, transition pace, and
a hot corner-3 zone) and asserts every category + flag the charter requires.

Run:  python -m backend.tests.test_basketball_scout
"""
from types import SimpleNamespace
from backend.services.tendency_engine.basketball_scout import build_scouting_report


def E(event_type, side="offense", result=None, **extra):
    return SimpleNamespace(event_type=event_type, side=side, result=result, extra_data=extra)


def build_events():
    ev = []

    # ── Category 1: #3 dominates possession (isolation dependency > 35%) ──
    # #3 long possessions (initiator), #5 quick catch-and-pass (ghost/dead-zone), #10 role.
    for _ in range(18):
        ev.append(E("possession", side="offense", primary_player_jersey="3",
                    possession_seconds=9.0, possession_origin="half_court",
                    score_diff_at_start=5, quarter=1))
    for _ in range(6):
        ev.append(E("possession", side="offense", primary_player_jersey="10",
                    possession_seconds=4.0, possession_origin="half_court",
                    score_diff_at_start=5, quarter=2))
    for _ in range(6):
        ev.append(E("possession", side="offense", primary_player_jersey="5",
                    possession_seconds=0.5, possession_origin="half_court",
                    score_diff_at_start=-3, quarter=4))
    # defensive possessions (for pace + deflection rates)
    for _ in range(20):
        ev.append(E("possession", side="defense", possession_seconds=15.0, quarter=1))
    # transition possessions (fast) to push transition frequency up
    for _ in range(8):
        ev.append(E("possession", side="offense", primary_player_jersey="3",
                    possession_seconds=4.0, possession_origin="transition",
                    score_diff_at_start=-4, quarter=4))

    # ── Category 2: #5 turnover-prone with a repeated pattern (bad_pass) ──
    for _ in range(4):
        ev.append(E("turnover", side="offense", primary_player_jersey="5",
                    turnover_type="bad_pass", game_situation="press",
                    generated_by_defender="21", quarter=3))
    ev.append(E("turnover", side="offense", primary_player_jersey="3",
                turnover_type="travel", game_situation="half_court", quarter=2))

    # ── Category 3: #21 is their best deflection defender (passing lane: wing_entry) ──
    for i in range(6):
        ev.append(E("deflection", side="defense", primary_player_jersey="21",
                    deflection_type="tipped_pass", resulted_in_possession_change=(i % 2 == 0),
                    passing_lane="wing_entry", quarter=2))
    ev.append(E("deflection", side="defense", primary_player_jersey="7",
                deflection_type="redirected_dribble", resulted_in_possession_change=False,
                passing_lane="post_entry", quarter=3))

    # ── Category 4 + 6: shots. #11 perimeter-dependent; hot Left Corner 3 zone ──
    # #11 heavy 3s
    for made in [True, True, False, True, False, True, False]:
        ev.append(E("shot", side="offense", result="made" if made else "missed",
                    primary_player_jersey="11", shot_zone="Left Corner 3", shot_type="3pt",
                    possession_origin="set", quarter=1, possession_seconds=8.0, score_diff_at_start=5))
    ev.append(E("shot", side="offense", result="made", primary_player_jersey="11",
                shot_zone="Restricted Area", shot_type="2pt", possession_origin="transition",
                quarter=2, possession_seconds=3.0))
    # #3 paint attacker
    for made in [True, True, False, True]:
        ev.append(E("shot", side="offense", result="made" if made else "missed",
                    primary_player_jersey="3", shot_zone="Restricted Area", shot_type="2pt",
                    possession_origin="pnr", quarter=1, possession_seconds=9.0, score_diff_at_start=5))
    # 4th quarter trailing: they jack threes (late-game shift)
    for made in [False, True, False, False]:
        ev.append(E("shot", side="offense", result="made" if made else "missed",
                    primary_player_jersey="11", shot_zone="Above-the-Break 3 Center", shot_type="3pt",
                    possession_origin="broken", quarter=4, possession_seconds=6.0, score_diff_at_start=-4))

    return ev


def approx(name, got, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}: {got}")
    return cond


def main():
    events = build_events()
    r = build_scouting_report(events)
    ok = True

    print("\n=== CATEGORY 1 — TIME OF POSSESSION (player-specific) ===")
    c1 = r["category_1_time_of_possession"]
    ok &= approx("primary ball-handler is #3", c1["primary_ball_handler"], c1["primary_ball_handler"] == "3")
    ok &= approx("isolation dependency flag (>35%)", c1["isolation_dependency_flag"], c1["isolation_dependency_flag"] is True)
    ok &= approx("primary share > 35%", c1["primary_share_pct"], c1["primary_share_pct"] > 35)
    ok &= approx("#5 flagged as dead-zone (catch & pass)", c1["dead_zone_players"], "5" in c1["dead_zone_players"])
    ok &= approx("#5 role is ghost", [p for p in c1["players"] if p["jersey"] == "5"][0]["role"],
                 [p for p in c1["players"] if p["jersey"] == "5"][0]["role"] == "ghost")

    print("\n=== CATEGORY 2 — TURNOVERS ===")
    c2 = r["category_2_turnovers"]
    top_to = c2["players"][0]
    ok &= approx("most turnovers is #5", top_to["jersey"], top_to["jersey"] == "5")
    ok &= approx("#5 pattern flag (2+ bad_pass)", top_to["pattern_flags"],
                 any(p["type"] == "bad_pass" and p["count"] >= 2 for p in top_to["pattern_flags"]))
    ok &= approx("rate per possession present", c2["team_rate_per_possession"], c2["team_rate_per_possession"] is not None)
    ok &= approx("rate per 10 min present", c2["team_rate_per_10_min"], c2["team_rate_per_10_min"] is not None)
    ok &= approx("defender #21 credited", c2["most_dangerous_defender"], c2["most_dangerous_defender"] == "21")

    print("\n=== CATEGORY 3 — DEFLECTIONS ===")
    c3 = r["category_3_deflections"]
    ok &= approx("neutralize-first defender is #21", c3["neutralize_first_defender"], c3["neutralize_first_defender"] == "21")
    ok &= approx("most vulnerable lane wing_entry", c3["most_vulnerable_lane"], c3["most_vulnerable_lane"] == "wing_entry")
    ok &= approx("possession-change conversion computed", c3["conversion_pct"], c3["conversion_pct"] > 0)

    print("\n=== CATEGORY 4 — 2PT vs 3PT RATIO ===")
    c4 = r["category_4_shot_ratio"]
    ok &= approx("#11 perimeter-dependent (>40% 3PA)", c4["perimeter_dependent_players"], "11" in c4["perimeter_dependent_players"])
    p3 = [p for p in c4["players"] if p["jersey"] == "3"][0]
    ok &= approx("#3 classified paint_attacker", p3["tendency"], p3["tendency"] == "paint_attacker")
    ok &= approx("late-game shift = jack threes", c4["late_game_shift"], c4["late_game_shift"] == "goes_small_jacks_threes")
    ok &= approx("by_half present", list(c4["by_half"].keys()), set(c4["by_half"].keys()) == {"first", "second"})

    print("\n=== CATEGORY 5 — PACE ===")
    c5 = r["category_5_pace"]
    ok &= approx("pace tracked", c5["tracked"], c5["tracked"] is True)
    ok &= approx("off & def possession seconds present", (c5["avg_offensive_possession_seconds"], c5["avg_defensive_possession_seconds"]),
                 c5["avg_offensive_possession_seconds"] is not None and c5["avg_defensive_possession_seconds"] is not None)
    ok &= approx("transition frequency computed", c5["transition_frequency_pct"], c5["transition_frequency_pct"] > 0)
    ok &= approx("pace_control classified", c5["pace_control"], c5["pace_control"] in ("coach_controlled", "player_driven"))

    print("\n=== CATEGORY 6 — SCORING AREAS (eFG%) ===")
    c6 = r["category_6_scoring_areas"]
    ok &= approx("team eFG% computed", c6["team_efg_pct"], c6["team_efg_pct"] > 0)
    lc3 = c6["zones"].get("Left Corner 3", {})
    ok &= approx("Left Corner 3 eFG% credits the three", lc3.get("efg_pct"), lc3.get("efg_pct", 0) > lc3.get("fg_pct", 0))
    ok &= approx("defensive priority zones flagged (>55% eFG)", c6["defensive_priority_zones"], len(c6["defensive_priority_zones"]) >= 1)
    ok &= approx("top scoring zones present", len(c6["top_scoring_zones"]), len(c6["top_scoring_zones"]) >= 1)

    print("\n=== GAME PLAN PRIORITIES (auto, Category 1 weighted heaviest) ===")
    gp = r["game_plan_priorities"]
    for item in gp:
        print(f"   {item['priority']}. [{item['category']}] {item['adjustment']}")
    ok &= approx("exactly top-3 priorities", len(gp), len(gp) == 3)
    ok &= approx("priority #1 is Time of Possession (heaviest)", gp[0]["category"], gp[0]["category"] == "Time of Possession")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
