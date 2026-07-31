"""
Shared foundation for §11 (Player One-Pager) and §12 (Heat Maps):
  A) eFG% + per-zone confidence in the basketball shot-zone map
  B) plainify() readability transform
  C) eFG -> color-band mapping with the "never RED on low confidence" rule
"""
from types import SimpleNamespace

from backend.services.tendency_engine.basketball import _shot_zone_map
from backend.services import plainify as P
from backend.services import heatmap as H


def _shot(zone, made, conf=0.9):
    return SimpleNamespace(event_type="shot", result=("made" if made else "miss"),
                           extra_data={"shot_zone": zone, "confidence": conf})


# ── A) eFG + confidence in the zone map ──────────────────────────────────────
def test_efg_credits_the_made_three():
    # Corner 3: 4 attempts, 2 made (both threes). FG 50%, eFG (2 + 0.5*2)/4 = 75%.
    shots = [_shot("Corner 3", True), _shot("Corner 3", True),
             _shot("Corner 3", False), _shot("Corner 3", False)]
    zm = _shot_zone_map(shots)["zones"]["Corner 3"]
    assert zm["fg_pct"] == 50.0
    assert zm["efg_pct"] == 75.0            # the extra point a made 3 is worth
    assert zm["confidence"] == 0.9


def test_efg_equals_fg_in_a_two_point_zone():
    shots = [_shot("Restricted Area", True), _shot("Restricted Area", True),
             _shot("Restricted Area", False), _shot("Restricted Area", False)]
    zm = _shot_zone_map(shots)["zones"]["Restricted Area"]
    assert zm["efg_pct"] == zm["fg_pct"] == 50.0


def test_zone_confidence_none_when_absent():
    shots = [SimpleNamespace(event_type="shot", result="made",
                             extra_data={"shot_zone": "Wing 3"})]  # no confidence
    assert _shot_zone_map(shots)["zones"]["Wing 3"]["confidence"] is None


# ── B) plainify ──────────────────────────────────────────────────────────────
def test_pct_to_words_bands():
    assert P.pct_to_words(78) == "almost always"
    assert P.pct_to_words(63) == "usually"
    assert P.pct_to_words(48) == "sometimes"
    assert P.pct_to_words(30) == "not often"
    assert P.pct_to_words(10) == "rarely"


def test_plainify_strips_percentages_and_jargon():
    out = P.plainify("They run ISO 78% of the time")
    assert "%" not in out and "78" not in out
    assert "one-on-one" in out
    assert "almost always" in out


def test_plainify_clamps_to_twelve_words():
    long = "They will attack the left side and the right side and the middle and everywhere else too"
    out = P.plainify(long)
    assert len(out.split()) <= 12
    assert P.has_readability_violation(out) is None


def test_readability_violation_detects_percent_and_length():
    assert P.has_readability_violation("shoots 55%") == "contains a percentage"
    assert P.has_readability_violation("one two three four five six seven eight nine ten eleven twelve thirteen")


# ── C) eFG band mapping + confidence downgrade ───────────────────────────────
def test_coach_bands_by_efg():
    assert H.efg_band_coach(60, 0.9)["band"] == "red"
    assert H.efg_band_coach(48, 0.9)["band"] == "orange"
    assert H.efg_band_coach(40, 0.9)["band"] == "yellow"
    assert H.efg_band_coach(20, 0.9)["band"] == "green"


def test_coach_red_downgraded_on_low_confidence():
    hi = H.efg_band_coach(60, 0.9)
    lo = H.efg_band_coach(60, 0.4)
    assert hi["band"] == "red" and hi["downgraded"] is False
    assert lo["band"] == "orange" and lo["downgraded"] is True   # never RED on low conf


def test_player_three_colors_and_downgrade():
    assert H.efg_band_player(60, 0.9)["band"] == "red"
    assert H.efg_band_player(60, 0.5)["band"] == "yellow"        # low conf -> not red
    assert H.efg_band_player(45, 0.9)["band"] == "yellow"
    assert H.efg_band_player(20, 0.9)["band"] == "green"
    # Unknown confidence counts as low -> a hot zone is watched, not feared.
    assert H.efg_band_player(60, None)["band"] == "yellow"
