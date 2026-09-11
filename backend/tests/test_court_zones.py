"""
Court-zone normalization — closes the seam between the vision detector's shot-zone
vocabulary and the scoring/scout engines.

Regression guard for the DHHS vs LHS report bug: the detector emitted "Left Wing 3"
/ "Right Wing 3" and the scout (which only knew "Above-the-Break 3 ...") counted
them as TWOS, producing a false "0% threes, wall off the paint" game plan. It also
counted "Free Throw Line" free throws as field goals, polluting eFG.

Run:  python -m backend.tests.test_court_zones
"""
from types import SimpleNamespace
from backend.services.tendency_engine import court_zones as cz
from backend.services.tendency_engine.basketball_scout import build_scouting_report


def E(event_type, side="offense", result=None, **extra):
    return SimpleNamespace(event_type=event_type, side=side, result=result, extra_data=extra)


def test_normalizer():
    # detector three-point variants fold into the canonical above-the-break bucket
    assert cz.normalize_zone("Left Wing 3") == "Above-the-Break 3 Left"
    assert cz.normalize_zone("Right Wing 3") == "Above-the-Break 3 Right"
    assert cz.normalize_zone("Top of Key 3") == "Above-the-Break 3 Center"
    # detector mid-range variants
    assert cz.normalize_zone("Right Elbow Mid") == "Mid-Range Right"
    assert cz.normalize_zone("Left Mid-Range") == "Mid-Range Left"
    # canonical labels round-trip unchanged
    assert cz.normalize_zone("Restricted Area") == "Restricted Area"
    assert cz.normalize_zone("Left Corner 3") == "Left Corner 3"
    # free throw is not a field-goal zone
    assert cz.normalize_zone("Free Throw Line") is None
    assert cz.is_free_throw_zone("Free Throw Line") is True
    # three detection through the normalizer
    assert cz.is_three_zone("Left Wing 3") is True
    assert cz.is_three_zone("Restricted Area") is False
    assert cz.is_paint_zone("Restricted Area") is True
    assert cz.is_mid_zone("Right Elbow Mid") is True
    # legacy / generic labels not in the alias table still classify (substring fallback,
    # mirrors the historical behavior so shot-zone maps keyed on raw labels don't regress)
    assert cz.is_three_zone("Corner 3") is True
    assert cz.is_mid_zone("Corner 3") is False
    assert cz.is_three_zone("Free Throw Line") is False
    # every label the detector emits is "known" (so the consistency gate stays quiet)
    for z in ("Left Wing 3", "Right Wing 3", "Top of Key 3", "Left Elbow Mid",
              "Right Mid-Range", "Free Throw Line", "Restricted Area", "Half Court"):
        assert cz.is_known_zone(z), z
    assert cz.is_known_zone("Klingon Zone") is False
    print("  normalizer: wing/elbow/free-throw mapping + three/paint/mid + known-set ✓")


def test_scout_counts_wing_threes_and_excludes_free_throws():
    ev = [
        # two wing threes (detector vocabulary) — must count as 3PA, not 2PA
        E("shot", side="offense", result="made", primary_player_jersey="5",
          shot_zone="Left Wing 3", shot_type="Pull-Up Jumper", quarter=2),
        E("shot", side="offense", result="missed", primary_player_jersey="5",
          shot_zone="Right Wing 3", shot_type="Pull-Up Jumper", quarter=2),
        # a rim make (2PA)
        E("shot", side="offense", result="made", primary_player_jersey="3",
          shot_zone="Restricted Area", shot_type="Layup", quarter=2),
        # two free throws — must be EXCLUDED from FGA / eFG entirely
        E("shot", side="offense", result="made", primary_player_jersey="3",
          shot_zone="Free Throw Line", shot_type="Free Throw", quarter=2),
        E("shot", side="offense", result="missed", primary_player_jersey="3",
          shot_zone="Free Throw Line", shot_type="Free Throw", quarter=2),
    ]
    rep = build_scouting_report(ev)
    c4 = rep["category_4_shot_ratio"]
    assert c4["attempts_3pt"] == 2, f"wing threes must count as 3PA, got {c4}"
    assert c4["attempts_2pt"] == 1, f"only the rim shot is a 2PA, got {c4}"
    assert c4["total_shots"] == 3, f"free throws must be excluded from FGA, got {c4}"
    assert c4["three_pt_rate_pct"] > 0, "three-point rate must not read 0% when they shot wing threes"

    c6 = rep["category_6_scoring_areas"]
    assert c6["total_shots"] == 3, f"eFG denominator excludes free throws, got {c6['total_shots']}"
    # wing threes are bucketed under the canonical above-the-break zone
    assert "Above-the-Break 3 Left" in c6["zones"], f"zones={list(c6['zones'])}"
    assert "Free Throw Line" not in c6["zones"], "free throws must not appear as a FG zone"
    print("  scout: wing threes counted as 3PA, free throws excluded from FGA/eFG ✓")


def run():
    test_normalizer()
    test_scout_counts_wing_threes_and_excludes_free_throws()
    print("\nALL COURT-ZONE ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
