"""
§12 Map 2 — individual player shot spots (per-player eFG by zone, hot/cold).
"""
from types import SimpleNamespace

from backend.services.tendency_engine.basketball import _player_shot_zones


def _shot(jersey, zone, made):
    return SimpleNamespace(event_type="shot", player=jersey, result=("made" if made else "miss"),
                           extra_data={"shot_zone": zone})


def test_per_player_zones_and_efg():
    shots = (
        # #34: 3 in the paint (2 made), 2 corner threes (2 made)
        [_shot("34", "Restricted Area", True), _shot("34", "Restricted Area", True),
         _shot("34", "Restricted Area", False),
         _shot("34", "Corner 3", True), _shot("34", "Corner 3", True)]
        # #7: only 2 shots -> below the 3-shot floor, excluded
        + [_shot("7", "Restricted Area", True), _shot("7", "Restricted Area", False)]
    )
    out = _player_shot_zones(shots)
    assert [p["jersey"] for p in out] == ["34"]          # #7 filtered out
    p = out[0]
    assert p["shots"] == 5
    zmap = {z["zone"]: z for z in p["zones"]}
    assert zmap["Restricted Area"]["efg_pct"] == round(2 / 3 * 100, 1)   # 2pt: eFG == FG
    assert zmap["Corner 3"]["efg_pct"] == 150.0                          # made threes credited
    assert "Corner 3" in p["hot_zones"]                                   # best eFG = hot


def test_jersey_hash_normalized_and_zoneless_shots_skipped():
    shots = [_shot("#12", "Wing 3", True)] * 3 + [
        SimpleNamespace(event_type="shot", player="12", result="made", extra_data={})  # no zone
    ]
    out = _player_shot_zones(shots)
    assert out and out[0]["jersey"] == "12"              # '#12' normalized to '12'
    assert all(z["zone"] for z in out[0]["zones"])       # zoneless shot excluded from zones


def test_empty():
    assert _player_shot_zones([]) == []
