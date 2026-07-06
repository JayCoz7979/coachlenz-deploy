"""
Module 9 — the four report formats (report_export.build_export).

Builds a representative football report dict (sections + scouting summary +
player_tendencies) and asserts each format returns the right, non-empty slice.

Run:  python -m backend.tests.test_report_export
"""
from backend.services.report_export import build_export, POSITION_UNITS


REPORT = {
    "title": "Football Scouting Report: Athens Golden Eagles",
    "sport": "football",
    "report_type": "opponent",
    "watermarked": False,
    "generated_at": "2026-07-06T18:00:00",
    "sections": [
        {"heading": "Executive Summary", "insight_type": "tendency", "body": "Run-first spread."},
        {"heading": "Opponent Offense — Run Game", "insight_type": "run", "body": "Inside zone heavy."},
        {"heading": "Opponent Offense — Pass Game", "insight_type": "pass", "body": "Four verticals on 3rd."},
        {"heading": "Opponent Defense — Fronts & Pressure", "insight_type": "defense", "body": "Edge blitz."},
        {"heading": "Opponent Defense — Coverage & Secondary", "insight_type": "defense", "body": "Cover 3 base."},
        {"heading": "Opponent Special Teams — Kicking Game", "insight_type": "special_teams", "body": "FG shaky 40+."},
        {"heading": "EXPLOITABLE OFFENSIVE PATTERNS", "insight_type": "tendency", "body": "Shotgun = run."},
    ],
    "summary": {
        "total_plays": 87,
        "scouting": {
            "report_status": "PRELIMINARY",
            "head_coach_priorities": [
                {"priority": 1, "phase": "DEF", "call": "TAKE AWAY Inside Zone", "confidence": "HIGH"},
                {"priority": 2, "phase": "OFF", "call": "Attack Cover 3 with four verticals", "confidence": "MEDIUM"},
                {"priority": 3, "phase": "ST", "call": "Return opportunity, coverage leaks", "confidence": "LOW"},
            ],
            "validation_gates": [
                {"gate": 6, "name": "Explosive Play Alert", "passed": False,
                 "alerts": [{"area": "Run concept", "concept": "Inside Zone", "explosive_rate_pct": 28.6}]},
            ],
        },
        "player_tendencies": {
            "tracked": True,
            "by_player": {
                "offense#22": {"jersey": "22", "team": "offense", "roles": {"RB": 12},
                               "touches": 20, "avg_yards": 6.1, "success_rate": 60.0,
                               "explosive_plays": 5, "as_runner": 18, "as_passer_or_receiver": 2,
                               "by_play_type": {"run": 18, "pass": 2}},
                "offense#7": {"jersey": "7", "team": "offense", "roles": {"WR": 9},
                              "touches": 9, "avg_yards": 11.0, "success_rate": 44.0,
                              "explosive_plays": 2, "as_runner": 0, "as_passer_or_receiver": 9,
                              "by_play_type": {"pass": 9}},
            },
        },
    },
}


def _headings(payload):
    return [b["heading"] for b in payload["blocks"]]


def run():
    # coordinator = every section
    c = build_export(REPORT, "coordinator")
    assert len(c["blocks"]) == len(REPORT["sections"]), "coordinator should include all sections"
    assert c["watermarked"] is False and c["sport"] == "football"
    print(f"  coordinator: {len(c['blocks'])} sections ✓")

    # head_coach = one-page priorities grouped by phase + explosive alert, NO full sections
    h = build_export(REPORT, "head_coach")
    hh = " | ".join(_headings(h))
    assert "Explosive Threats" in hh, f"expected explosive threat block, got {hh}"
    assert any("Defense" in x for x in _headings(h)) and any("Offense" in x for x in _headings(h))
    assert len(h["blocks"]) <= 5, "head coach summary must stay tight (one page)"
    print(f"  head_coach: {_headings(h)} ✓")

    # position (DB) = pass-game + coverage sections, plus exec/exploitable context
    d = build_export(REPORT, "position", unit="DB")
    dh = " | ".join(_headings(d))
    assert "Pass Game" in dh, f"DB brief should include the pass game, got {dh}"
    assert "Run Game" not in dh, f"DB brief should NOT include the run game, got {dh}"
    assert d["subtitle"].endswith("Defensive Backs")
    print(f"  position/DB: {_headings(d)} ✓")

    # position (OL) = fronts & pressure, not coverage
    o = build_export(REPORT, "position", unit="OL")
    oh = " | ".join(_headings(o))
    assert "Fronts & Pressure" in oh, f"OL brief should include fronts/pressure, got {oh}"
    print(f"  position/OL: {_headings(o)} ✓")

    # player = one bulletin per identified player, with a cue
    p = build_export(REPORT, "player")
    assert len(p["blocks"]) == 2, f"expected 2 player bulletins, got {len(p['blocks'])}"
    rb = next(b for b in p["blocks"] if b["heading"].startswith("#22"))
    assert "big-play threat" in rb["body"], f"RB #22 (5 expl/20) should be a big-play threat: {rb['body']}"
    assert "Your job:" in rb["body"]
    print(f"  player: {_headings(p)} ✓")

    # player filtered to one jersey
    one = build_export(REPORT, "player", player="7")
    assert len(one["blocks"]) == 1 and one["blocks"][0]["heading"].startswith("#7")
    print(f"  player #7 only: {_headings(one)} ✓")

    # unknown format rejected
    try:
        build_export(REPORT, "bogus")
        assert False, "unknown format should raise"
    except ValueError:
        pass

    assert set(POSITION_UNITS) >= {"OL", "DL", "WR", "DB", "QB", "LB", "RB", "ST"}
    print("\nALL REPORT EXPORT ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
