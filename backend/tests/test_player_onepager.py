"""
§11 Player One-Pager export format.

Verifies the one-pager is built from structured data for both sports, that the
static 3-color heat map keys off eFG + confidence, and — the hard §11 rule — that
NO player-facing string carries a percentage or runs longer than 12 words.
"""
from backend.services.report_export import build_export, CONFIDENTIAL_NOTE
from backend.services.plainify import has_readability_violation


def _all_strings(out):
    """Every player-facing string in a one-pager payload."""
    s = []
    if out.get("key"):
        s.append(out["key"])
    s += [w["cue"] for w in out.get("watch", [])]
    s += list(out.get("run", []))
    s += list(out.get("do", []))
    return s


def _assert_readable(out):
    for text in _all_strings(out):
        assert has_readability_violation(text) is None, f"readability: {text!r}"


# ── basketball ───────────────────────────────────────────────────────────────
def _bball_report():
    return {
        "title": "Eagles", "sport": "basketball",
        "summary": {
            "scouting": {"game_plan_priorities": [
                {"adjustment": "Deny #12 the ball. They control 45% of possession time; trap on the catch."},
                {"adjustment": "Pressure #7 (3 turnovers). Turn them over early to set tempo."},
            ]},
            "shooting_overview": {"three_point": {"pct_of_shots": 40}},
            "shot_zone_map": {
                "most_frequent_zone": "Corner 3",
                "zones": {
                    "Corner 3": {"attempts": 10, "efg_pct": 60.0, "confidence": 0.9},
                    "Restricted Area": {"attempts": 6, "efg_pct": 30.0, "confidence": 0.9},
                },
            },
            "shot_creation": {"best_action": "Spot-Up"},
            "player_tendencies": {"by_player": {
                "off#12": {"jersey": "12", "shot_tendency": "perimeter", "perimeter_dependency_flag": True},
                "off#7": {"jersey": "7", "possession_role": "initiator"},
            }},
        },
    }


def test_basketball_onepager_structure_and_readability():
    out = build_export(_bball_report(), "player_onepager")
    assert out["format"] == "player_onepager"
    assert out["key"] and "%" not in out["key"]
    assert [w["jersey"] for w in out["watch"]] == ["12", "7"]
    assert "They shoot lots of threes." in out["run"]
    assert any("the corner" in r for r in out["run"])
    assert out["do"] and len(out["do"]) <= 3
    assert out["confidential_note"] == CONFIDENTIAL_NOTE
    _assert_readable(out)


def test_basketball_heatmap_bands_from_efg():
    out = build_export(_bball_report(), "player_onepager")
    cells = {c["zone"]: c["band"] for c in out["heatmap"]["zones"]}
    assert cells["the corner"] == "red"     # eFG 60, high confidence
    assert cells["the paint"] == "green"    # eFG 30


def test_low_confidence_hot_zone_is_not_red():
    r = _bball_report()
    r["summary"]["shot_zone_map"]["zones"]["Corner 3"]["confidence"] = 0.4
    out = build_export(r, "player_onepager")
    cells = {c["zone"]: c["band"] for c in out["heatmap"]["zones"]}
    assert cells["the corner"] == "yellow"  # never RED on a shaky read


# ── football ─────────────────────────────────────────────────────────────────
def _fball_report():
    return {
        "title": "Tigers", "sport": "football",
        "summary": {
            "scouting": {"head_coach_priorities": [
                {"call": "Stop their inside zone on early downs; they run 78% of the time.", "confidence": "HIGH"},
            ]},
            "offense": {
                "run_pass_ratio": {"run_pct": 68.0, "pass_pct": 32.0},
                "top_formations": {"I-Form": 10, "Shotgun": 4},
                "top_plays": {"Inside Zone": 8},
            },
            "player_tendencies": {"by_player": {
                "off#22": {"jersey": "22", "touches": 20, "as_runner": 15,
                           "as_passer_or_receiver": 0, "explosive_plays": 4, "success_rate": 60},
            }},
        },
    }


def test_football_onepager_run_and_readability():
    out = build_export(_fball_report(), "player_onepager")
    assert any("run the ball" in r for r in out["run"])     # 68% run -> plain
    assert any("I-Form" in r for r in out["run"])
    assert out["heatmap"] is None                            # football spatial map is a §12 follow-up
    assert out["key"] and "%" not in out["key"]
    _assert_readable(out)


def test_thin_report_degrades_gracefully():
    out = build_export({"title": "X", "sport": "basketball", "summary": {}}, "player_onepager")
    assert out["format"] == "player_onepager"
    assert out["watch"] == [] and out["run"] == [] and out["do"] == []
    _assert_readable(out)
