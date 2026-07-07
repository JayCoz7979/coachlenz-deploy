"""
Synthetic-data test for the basketball COORDINATOR scouting layer
(basketball_scout_validation) — the eight validation gates, situational
statements, the installable game plan, the late-game alert, free-throw strategic
targets, special situations, and the single-camera confidence summary.

Builds a realistic 3-game opponent sample (80+ possessions) with:
  • a dominant ball-handler (#3, > 35% of possession time)      -> C1 / DEF trap
  • a turnover-prone guard (#5, repeated bad-pass pattern)       -> C2 / pressure
  • a perimeter-dependent shooter (#7, > 40% threes)            -> C4 / run off line
  • a hot corner-3 zone (eFG > 55%)                             -> C6 / take away
  • one player taking > 40% of late one-possession shots (#3)   -> Gate 7 alert
  • a 45% free-throw shooter (#5) and a 92% shooter (#7)        -> foul / never-foul
  • a BLOB set run twice late & close                          -> special situations
  • a player grade on < 5 visible looks                        -> Gate 5 ESTIMATE
  • intake: analyst but NO reviewer + an injury flag + poor camera
        -> Gate 2 fail, Gate 8 personnel flag, camera penalty

Run:  python -m backend.tests.test_basketball_scout_validation
"""
from types import SimpleNamespace

from backend.services.tendency_engine.basketball_scout import build_scouting_report
from backend.services.tendency_engine.basketball_scout_validation import (
    build_basketball_scouting_report,
)


def E(event_type, side="offense", result=None, **extra):
    return SimpleNamespace(event_type=event_type, side=side, result=result,
                           player=extra.get("primary_player_jersey"), extra_data=extra)


def META(**kw):
    return SimpleNamespace(event_type="scout_meta", side="meta", result=None,
                           player=None, extra_data=kw)


def build_events():
    ev = [META(
        analyst_id="coach_a", analyst="coach_a",
        reviewer_id=None, reviewer=None,          # no reviewer -> Gate 2 fails
        status="draft",
        games_scouted=3,
        injury_flags=["Starting C out Game 3"],    # -> Gate 8 personnel flag
        games_with_missing_starter=[3],
        camera_angle="high and wide", camera_quality="poor",   # -> camera penalty
        off_ball_visibility_pct=72,
    )]

    def g(i):  # spread evenly across 3 games
        return (i % 3) + 1

    # ── C1: #3 dominates possession (isolation dependency > 35%) ──
    for i in range(30):
        ev.append(E("possession", side="offense", primary_player_jersey="3",
                    possession_seconds=9.0, possession_origin="half_court",
                    score_diff_at_start=5, quarter=1, game_number=g(i)))
    for i in range(10):
        ev.append(E("possession", side="offense", primary_player_jersey="10",
                    possession_seconds=4.0, possession_origin="half_court",
                    score_diff_at_start=5, quarter=2, game_number=g(i)))
    for i in range(8):
        ev.append(E("possession", side="offense", primary_player_jersey="5",
                    possession_seconds=0.5, possession_origin="half_court",
                    score_diff_at_start=-3, quarter=2, game_number=g(i)))
    # transition possessions (fast) to push transition frequency up
    for i in range(10):
        ev.append(E("possession", side="offense", primary_player_jersey="3",
                    possession_seconds=4.0, possession_origin="transition",
                    score_diff_at_start=-4, quarter=3, game_number=g(i)))
    # defensive possessions (for Gate 1 total >= 80 and pace)
    for i in range(30):
        ev.append(E("possession", side="defense", possession_seconds=15.0,
                    quarter=1, game_number=g(i)))

    # ── C2: #5 turnover-prone with a repeated pattern (bad_pass) ──
    for i in range(4):
        ev.append(E("turnover", side="offense", primary_player_jersey="5",
                    turnover_type="bad_pass", game_situation="press",
                    generated_by_defender="21", quarter=3, game_number=g(i)))

    # ── C4 + C6: #7 perimeter-dependent, hot Right Corner 3 ──
    for i in range(10):
        made = i % 2 == 0
        ev.append(E("shot", side="offense", result="made" if made else "missed",
                    primary_player_jersey="7", shot_zone="Right Corner 3", shot_type="3pt",
                    possession_origin="half_court", quarter=1, game_number=g(i)))
    for i in range(3):
        ev.append(E("shot", side="offense", result="made" if i == 0 else "missed",
                    primary_player_jersey="7", shot_zone="Restricted Area", shot_type="2pt",
                    quarter=2, game_number=g(i)))
    # a couple paint looks from #3 so the shot diet isn't purely threes
    for i in range(4):
        ev.append(E("shot", side="offense", result="made" if i < 2 else "missed",
                    primary_player_jersey="3", shot_zone="Restricted Area", shot_type="2pt",
                    quarter=1, game_number=g(i)))

    # ── Gate 7: late & close — #3 takes the lion's share of shots ──
    for i in range(6):
        ev.append(E("shot", side="offense", result="made" if i % 3 == 0 else "missed",
                    primary_player_jersey="3", shot_zone="Above-the-Break 3 Center",
                    shot_type="3pt", quarter=4, score_diff_at_start=-2, game_number=g(i)))
    ev.append(E("shot", side="offense", result="missed", primary_player_jersey="10",
                shot_zone="Mid-Range Center", shot_type="2pt", quarter=4,
                score_diff_at_start=-2, game_number=1))

    # ── Module 8: free throws — #5 a 45% shooter (foul), #7 a 92% shooter (never) ──
    #   #5: 20 attempts, 9 makes = 45%
    for i in range(10):
        ev.append(E("free_throw", side="offense", primary_player_jersey="5",
                    attempts=2, makes=[1, 0, 1, 1, 0, 1, 0, 1, 1, 0][i % 10] and 1 or 0,
                    pressure_situation=(i >= 8), shooter_tempo="quick",
                    box_out_formation_defense="standard", game_number=g(i)))
    #   #7: 13 attempts, 12 makes = 92%
    for i in range(13):
        ev.append(E("free_throw", side="offense", primary_player_jersey="7",
                    attempts=1, makes=0 if i == 0 else 1, shooter_tempo="routine",
                    game_number=g(i)))

    # ── Module 7: a BLOB set run twice late & close (trusted) ──
    for i in range(2):
        ev.append(E("special_situation", side="offense", situation_type="BLOB",
                    formation="Box", primary_action="screen the screener", target="7",
                    result="made", late_and_close=True, quarter=4, game_number=g(i)))
    ev.append(E("special_situation", side="offense", situation_type="SLOB",
                formation="Stack", primary_action="pop the big", result="missed",
                late_and_close=False, quarter=2, game_number=1))

    # ── Module 5 + Gate 5: a grade resting on < 5 visible looks -> ESTIMATE ──
    ev.append(E("player_profile", side="meta", jersey="3", position="PG",
                handedness="right", role="primary_ball_handler",
                driving_grade=4, visible_examples=3))
    ev.append(E("player_profile", side="meta", jersey="7", position="SG",
                handedness="right", role="3-and-D", catch_shoot_grade=5,
                visible_examples=8))
    return ev


def run():
    ev = build_events()
    six_cat = build_scouting_report(ev)
    # `summary` is the deep basketball analysis dict; the coordinator reads a few
    # of its keys defensively (defensive_scheme / ball_screen_defense), so an empty
    # dict is a valid minimal input that exercises the guarded paths.
    summary = {}
    scouting = build_basketball_scouting_report(ev, summary, six_cat)

    assert scouting["available"], "scouting block should be available"
    # Backward-compat: the six categories + priorities must still be present.
    for k in ("category_1_time_of_possession", "category_6_scoring_areas", "game_plan_priorities"):
        assert k in scouting, f"missing backward-compat key {k}"

    # ── Gates ───────────────────────────────────────────────────────────────
    gates = {g["gate"]: g for g in scouting["validation_gates"]}
    assert set(gates) == {1, 2, 3, 4, 5, 6, 7, 8}, f"all eight gates present, got {set(gates)}"
    print(f"  Report status: {scouting['report_status']}  "
          f"(possessions={scouting['total_possessions']}, games={scouting['games_scouted']})")

    # Gate 1: 80+ possessions across 3 games -> FINAL.
    assert gates[1]["passed"] is True, f"Gate 1 should pass: {gates[1]['notes']}"
    assert scouting["report_status"] == "FINAL"
    print(f"  Gate 1 (possession count): passed={gates[1]['passed']} — {gates[1]['notes'][0]}")

    # Gate 2: no reviewer -> fail.
    assert gates[2]["passed"] is False, "Gate 2 must fail with no reviewer"
    print(f"  Gate 2 (dual review): passed={gates[2]['passed']} — {gates[2]['notes'][0]}")

    # Gate 4: consistency -> pass (log matches).
    assert gates[4]["passed"] is True, f"Gate 4 discrepancies: {gates[4].get('discrepancies')}"
    print(f"  Gate 4 (consistency): passed={gates[4]['passed']}")

    # Gate 5: #3 grade on 3 looks -> at least one ESTIMATE.
    assert gates[5]["passed"] is False, "Gate 5 should flag the < 5-look grade"
    assert gates[5]["estimate_grades"] >= 1
    print(f"  Gate 5 (visibility): passed={gates[5]['passed']} — {gates[5]['notes'][0]}")

    # Gate 6: game plan translated -> pass.
    assert gates[6]["passed"] is True, "Gate 6 should pass once game plan is built"
    print(f"  Gate 6 (translation): passed={gates[6]['passed']} — {gates[6]['notes'][0]}")

    # Gate 7: #3 dominates late shots -> alert.
    assert gates[7]["passed"] is False, "Gate 7 should fire the late-game alert"
    assert scouting["late_game_profile"]["primary_threat"] == "3"
    print(f"  Gate 7 (late-game): threat=#{scouting['late_game_profile']['primary_threat']} "
          f"({scouting['late_game_profile']['primary_threat_share_pct']}% of late shots)")

    # Gate 8: injury flag -> personnel flagged.
    assert scouting["personnel_flagged"] is True and gates[8]["passed"] is False
    print(f"  Gate 8 (personnel): flagged=True — {gates[8]['notes'][0]}")

    # ── Situational statements (personnel flag asterisks every line) ─────────
    stmts = scouting["situational_tendencies"]
    assert stmts, "expected situational statements"
    assert all(s["statement"].endswith("*") for s in stmts), "personnel flag should asterisk every statement"
    print(f"\n  Situational statements ({len(stmts)}):")
    for s in stmts[:5]:
        print(f"    [{s['confidence']}] {s['statement']}  (n={s['sample']})")

    # ── Game plan ────────────────────────────────────────────────────────────
    gp = scouting["game_plan"]
    assert gp["defensive_plan"], "defensive plan should have items"
    # The late-game threat should lead the defensive plan (featured).
    top_def = gp["defensive_plan"][0]
    assert "FINAL 4:00" in top_def["call"] or "#3" in top_def["call"], \
        f"top def call should feature the late threat, got {top_def['call']}"
    print(f"\n  DEFENSE plan (top 4):")
    for it in gp["defensive_plan"][:4]:
        print(f"    - {it['call']}  [{it['confidence']}, n={it['sample']}, {it['class']}]")
    print(f"  OFFENSE plan:")
    for it in gp["offensive_plan"]:
        print(f"    - {it['call']}  [{it['confidence']}, n={it['sample']}, {it['class']}]")
    print(f"  SPECIAL SITUATIONS plan:")
    for it in gp["special_situations_plan"]:
        print(f"    - {it['call']}  [{it['confidence']}, n={it['sample']}, {it['class']}]")

    # ── Free throws ──────────────────────────────────────────────────────────
    ft = scouting["free_throw_profile"]
    targets = [t["jersey"] for t in ft["strategic_foul_targets"]]
    never = [t["jersey"] for t in ft["never_foul_players"]]
    assert "5" in targets, f"#5 (45% FT) should be a strategic foul target, got {targets}"
    assert "7" in never, f"#7 (92% FT) should be never-foul, got {never}"
    print(f"\n  Free throws: strategic foul targets={targets}, never-foul={never}, "
          f"team {ft['team_ft_pct']}%")

    # ── Special situations ───────────────────────────────────────────────────
    ss = scouting["special_situations"]
    assert ss["tracked"] and "BLOB" in ss["by_type"]
    assert ss["by_type"]["BLOB"]["trusted_late_sets"], "BLOB run 2x late & close should be trusted"
    print(f"  Special situations: BLOB trusted late sets = "
          f"{[t['set'] for t in ss['by_type']['BLOB']['trusted_late_sets']]}")

    # ── Advanced metrics + camera ────────────────────────────────────────────
    adv = scouting["advanced_metrics"]
    print(f"  Advanced: PPP={adv['points_per_possession']}, "
          f"shot dist={adv['shot_distribution']}")
    cam = scouting["camera_confidence"]
    assert cam["individual_grade_penalty"] is True, "poor camera quality should penalize individual grades"
    print(f"  Camera: {cam['visibility_rating']} — penalty={cam['individual_grade_penalty']}")

    # ── Head coach digest ────────────────────────────────────────────────────
    hc = scouting["head_coach_priorities"]
    assert hc and hc[0]["priority"] == 1
    print(f"\n  Head coach priorities ({len(hc)}):")
    for p in hc:
        print(f"    {p['priority']}. [{p['phase']}] {p['call']} ({p['confidence']})")

    # ── Gate 2 lifecycle: a distinct reviewer signing off flips it to pass ────
    ev2 = build_events()
    for e in ev2:
        if e.event_type == "scout_meta":
            e.extra_data["reviewer_id"] = "coach_b"
            e.extra_data["reviewer"] = "coach_b"
            e.extra_data["status"] = "reviewed"
    six2 = build_scouting_report(ev2)
    scouting2 = build_basketball_scouting_report(ev2, {}, six2)
    g2 = {g["gate"]: g for g in scouting2["validation_gates"]}[2]
    assert g2["passed"] is True, f"Gate 2 should pass with a distinct reviewer: {g2['notes']}"
    print(f"\n  Gate 2 lifecycle: reviewed by distinct reviewer -> passed={g2['passed']}")

    print("\nALL BASKETBALL COORDINATOR ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
