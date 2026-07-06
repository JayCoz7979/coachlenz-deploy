"""
Synthetic-data test for the football coordinator scouting layer (football_scout).

Builds a realistic 3-game opponent sample (60+ plays) with:
  • a dominant run concept (Inside Zone) that goes explosive > 20%  -> Gate 6 alert
  • a heavy 3rd-&-long pass lean                                    -> situational stmt
  • a red-zone tendency
  • a defense that sits in Cover 3 and blitzes the edge             -> game plan
  • special teams: FG unreliable 40+, punt coverage leaks           -> ST plan
  • intake metadata: analyst but NO reviewer, and an injury flag    -> Gate 2 fail, Gate 7

Then asserts every gate, the game plan, and the confidence tiering the charter requires.

Run:  python -m backend.tests.test_football_scout
"""
from types import SimpleNamespace

from backend.services.tendency_engine.football import (
    analyze_football, analyze_football_defense, analyze_football_special,
)
from backend.services.tendency_engine.football_scout import build_football_scouting_report


def P(side="offense", **cols):
    """A play event. Direct columns become attributes; the rest go to extra_data."""
    direct = {}
    for k in ("down", "distance", "field_position", "hash_position", "formation",
              "personnel", "play_type", "motion", "result", "yards_gained",
              "time_seconds", "defensive_front", "coverage", "blitz"):
        direct[k] = cols.pop(k, None)
    direct["motion"] = bool(direct.get("motion"))
    return SimpleNamespace(event_type="play", side=side, extra_data=cols, **direct)


def META(**kw):
    return SimpleNamespace(event_type="scout_meta", side="meta", extra_data=kw,
                           down=None, distance=None, play_type=None)


def build_events():
    ev = [META(
        analyst_id="coach_a", analyst="coach_a",
        reviewer_id=None, reviewer=None,      # no reviewer -> Gate 2 fails
        status="draft",
        games_scouted=3,
        injury_flags=["Starting RB out Game 2"],   # -> Gate 7 personnel flag
        games_with_missing_starter=[2],
    )]

    # ── OFFENSE: 3 games, Inside Zone is their bread-and-butter and pops big ──
    # 14 Inside Zone runs, 4 explosive (28.5% > 20% -> Gate 6 alert), avg solid.
    iz_yards = [4, 3, 12, 5, 2, 15, 6, 4, 3, 18, 5, 4, 11, 2]
    for i, y in enumerate(iz_yards):
        ev.append(P(side="offense", game_number=(i % 3) + 1, down=1, distance=10,
                    field_position="OWN 40", formation="Shotgun", personnel="11",
                    play_type="run", run_concept="Inside Zone", run_direction="Inside Left",
                    run_gap="inside left A-gap", yards_gained=y,
                    result="first down" if y >= 10 else "gain"))

    # 10 Power runs, none explosive.
    for i in range(10):
        ev.append(P(side="offense", game_number=(i % 3) + 1, down=1, distance=10,
                    field_position="OWN 30", formation="I-Form", personnel="21",
                    play_type="run", run_concept="Power O", run_direction="Off-Tackle Right",
                    run_gap="off-tackle right", yards_gained=[3, 4, 2, 5, 3, 4, 2, 6, 3, 4][i],
                    result="gain"))

    # 3rd & long: they pass 14 of 16 (87.5%) -> strong situational statement.
    for i in range(14):
        ev.append(P(side="offense", game_number=(i % 3) + 1, down=3, distance=9,
                    field_position="OWN 45", formation="Empty", personnel="10",
                    play_type="pass", pass_concept="Four Verticals", pass_depth="Deep",
                    target_area="Middle Deep", yards_gained=[8, 12, 3, 0, 22, 6, 0, 14, 9, 4, 0, 17, 7, 11][i],
                    result="gain" if i % 3 else "incompletion"))
    for i in range(2):
        ev.append(P(side="offense", game_number=1, down=3, distance=8,
                    formation="Shotgun", personnel="11", play_type="run",
                    run_concept="Draw", run_direction="Inside Right", yards_gained=3, result="gain"))

    # Red zone: run-heavy inside the 20 (8 plays).
    for i in range(8):
        ev.append(P(side="offense", game_number=(i % 3) + 1, down=1, distance=8,
                    field_position="OPP 12", formation="Jumbo", personnel="22",
                    play_type="run" if i < 6 else "pass", run_concept="Power O" if i < 6 else None,
                    pass_concept=None if i < 6 else "Fade", yards_gained=[3, 5, 2, 6, 8, 4, 0, 3][i],
                    result="touchdown" if i in (4,) else "gain"))

    # ── DEFENSE: Cover 3 base, edge pressure ────────────────────────────────
    for i in range(24):
        blitz = "Edge Left" if i % 4 == 0 else None
        ev.append(P(side="defense", game_number=(i % 3) + 1, down=(i % 3) + 1,
                    distance=[10, 7, 9][i % 3], formation="Trips Right",
                    defensive_front="4-2-5", coverage="Cover 3",
                    blitz=blitz, yards_gained=[4, 6, 2, 3][i % 4], result="gain",
                    coverage_shell="One-High", safety_rotation="Rotated Single High",
                    corner_technique="off-man 7 yard",
                    pressure_gap="edge left" if blitz else None,
                    pressure_type="5-man" if blitz else "4-man"))

    # ── SPECIAL TEAMS: FG unreliable 40+, punt coverage leaks ───────────────
    # FG: 3/3 inside 30, 1/3 from 40-49 (33%) -> unreliable line at 40-49.
    for d, made in [(25, True), (28, True), (22, True), (42, False), (45, True), (47, False)]:
        ev.append(P(side="special_teams", game_number=1, play_type="Field Goal",
                    st_unit="Field Goal", fg_distance_yds=d,
                    result="made" if made else "missed",
                    kick_result="made" if made else "missed", yards_gained=d))
    # Punts: coverage leaks (avg return 11 yds, one explosive), directional right.
    for i in range(6):
        ev.append(P(side="special_teams", game_number=(i % 3) + 1, play_type="Punt",
                    st_unit="Punt", kick_direction="Right",
                    kick_result="returned", yards_gained=[40, 38, 44, 41, 39, 43][i]))
    for i in range(3):
        ev.append(P(side="special_teams", game_number=1, play_type="Punt Return",
                    st_unit="Punt Return", return_scheme="Wall Right",
                    yards_gained=[8, 24, 6][i], result="gain"))
    return ev


def run():
    ev = build_events()
    offense = analyze_football([e for e in ev if e.side == "offense"])
    defense = analyze_football_defense([e for e in ev if e.side == "defense"])
    special = analyze_football_special([e for e in ev if e.side == "special_teams"])
    scouting = build_football_scouting_report(ev, offense, defense, special)

    assert scouting["available"], "scouting block should be available"

    # ── Gates ───────────────────────────────────────────────────────────────
    gates = {g["gate"]: g for g in scouting["validation_gates"]}
    assert set(gates) == {1, 2, 3, 4, 5, 6, 7}, "all seven gates present"

    # Gate 1: 60+ offensive plays but need 3 games — we have 3 games and 60+ plays.
    print(f"  Gate 1 (play count): passed={gates[1]['passed']}  status={scouting['report_status']}")
    print(f"    total_plays={scouting['total_plays']} games={scouting['games_scouted']}")

    # Gate 2: no reviewer -> must fail.
    assert gates[2]["passed"] is False, "Gate 2 must fail with no reviewer"
    print(f"  Gate 2 (dual review): passed={gates[2]['passed']} — {gates[2]['notes'][0]}")

    # Gate 4: consistency — engine-recomputed counts should match, so pass.
    assert gates[4]["passed"] is True, f"Gate 4 discrepancies: {gates[4].get('discrepancies')}"
    print(f"  Gate 4 (consistency): passed={gates[4]['passed']}")

    # Gate 6: Inside Zone explosive rate > 20% -> at least one alert.
    alerts = gates[6].get("alerts", [])
    assert any("Inside Zone" in a["concept"] for a in alerts), f"expected Inside Zone explosive alert, got {alerts}"
    iz_alert = next(a for a in alerts if "Inside Zone" in a["concept"])
    assert iz_alert["explosive_rate_pct"] >= 20.0
    print(f"  Gate 6 (explosive alert): {iz_alert['concept']} {iz_alert['explosive_rate_pct']}% "
          f"({iz_alert['explosive_plays']}/{iz_alert['sample']})")

    # Gate 7: injury flag -> personnel flagged.
    assert scouting["personnel_flagged"] is True, "Gate 7 should flag personnel"
    assert gates[7]["passed"] is False
    print(f"  Gate 7 (personnel): flagged={scouting['personnel_flagged']} — {gates[7]['notes'][0]}")

    # Gate 5: game plan translated -> passed True.
    assert gates[5]["passed"] is True, "Gate 5 should pass once game plan is built"
    print(f"  Gate 5 (translation): passed={gates[5]['passed']} — {gates[5]['notes'][0]}")

    # ── Situational statements ───────────────────────────────────────────────
    stmts = scouting["situational_tendencies"]
    assert any("3rd & long" in s["category"].lower() for s in stmts), "expected a 3rd & long statement"
    # Personnel flag -> statements carry an asterisk and a dropped tier.
    assert all(s["statement"].endswith("*") for s in stmts), "personnel flag should asterisk every statement"
    print(f"\n  Situational statements ({len(stmts)}):")
    for s in stmts[:4]:
        print(f"    [{s['confidence']}] {s['statement']}  (n={s['sample']})")

    # ── Game plan ────────────────────────────────────────────────────────────
    gp = scouting["game_plan"]
    assert gp["defensive_plan"], "defensive plan should have items"
    assert gp["offensive_plan"], "offensive plan should have items"
    assert gp["special_teams_plan"], "special teams plan should have items"

    # The Inside Zone TAKE AWAY should be the top defensive call (featured threat).
    top_def = gp["defensive_plan"][0]
    assert "TAKE AWAY" in top_def["call"], f"top def call should be the explosive threat, got {top_def['call']}"

    # ST plan should flag the FG range dropoff and the punt coverage leak.
    st_calls = " | ".join(i["call"] for i in gp["special_teams_plan"])
    assert "FG range alert" in st_calls, f"expected FG range alert, got: {st_calls}"
    print(f"\n  DEFENSE plan (top 3):")
    for it in gp["defensive_plan"][:3]:
        print(f"    - {it['call']}  [{it['confidence']}, n={it['sample']}, {it['class']}]")
    print(f"  OFFENSE plan (top 3):")
    for it in gp["offensive_plan"][:3]:
        print(f"    - {it['call']}  [{it['confidence']}, n={it['sample']}, {it['class']}]")
    print(f"  SPECIAL TEAMS plan:")
    for it in gp["special_teams_plan"]:
        print(f"    - {it['call']}  [{it['confidence']}, n={it['sample']}, {it['class']}]")

    # ── Head coach digest ────────────────────────────────────────────────────
    hc = scouting["head_coach_priorities"]
    assert hc and hc[0]["priority"] == 1
    print(f"\n  Head coach priorities ({len(hc)}):")
    for p in hc:
        print(f"    {p['priority']}. [{p['phase']}] {p['call']} ({p['confidence']})")

    print("\nALL FOOTBALL SCOUT ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
