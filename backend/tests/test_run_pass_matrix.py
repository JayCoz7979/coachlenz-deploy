"""
§12 Map 4 — Run/Pass tendency matrix (Down x Distance, cell = run%, 5-band color).

Distance replaced hash as the column axis: down-and-distance is the classic
tendency coaches want, and `distance` is far more readable on single-camera film
than `hash_position` (which the wide fixed angle usually can't resolve).
"""
from types import SimpleNamespace

from backend.services.tendency_engine.football import _run_pass_matrix, _distance_bucket
from backend.services.heatmap import run_pass_band


def _p(kind, down, dist):
    return SimpleNamespace(event_type=kind, play_type=None, down=down, distance=dist,
                           hash_position=None, yards_gained=None, side="offense")


def _plays():
    plays = []
    # 1st & Long (10): 6 run / 2 pass -> 75% run -> RED
    plays += [_p("run", 1, 10)] * 6 + [_p("pass", 1, 10)] * 2
    # 3rd & Long (8): 1 run / 5 pass -> ~17% run -> PURPLE (pass heavy)
    plays += [_p("run", 3, 8)] * 1 + [_p("pass", 3, 8)] * 5
    # 2nd & Short (2): 1 run / 1 pass -> total 2 < 4 -> low sample, grey
    plays += [_p("run", 2, 2), _p("pass", 2, 2)]
    return plays


# ── distance bucketing ───────────────────────────────────────────────────────
def test_distance_buckets():
    assert _distance_bucket(1) == "Short"
    assert _distance_bucket(3) == "Short"
    assert _distance_bucket(4) == "Medium"
    assert _distance_bucket(6) == "Medium"
    assert _distance_bucket(7) == "Long"
    assert _distance_bucket(15) == "Long"
    assert _distance_bucket(0) == "Short"       # goal-to-go / inches
    assert _distance_bucket(None) is None
    assert _distance_bucket("x") is None


def test_matrix_shape_and_ordering():
    m = _run_pass_matrix(_plays())
    assert m["rows"] == ["1st", "2nd", "3rd"]
    assert m["cols"] == ["Short", "Long"]        # canonical distance order, Medium absent
    assert m["min_sample"] == 4
    assert m["axis"] == "distance"


def test_run_heavy_cell_is_red():
    c = _run_pass_matrix(_plays())["cells"]["1st"]["Long"]
    assert c["run_pct"] == 75.0 and c["run"] == 6 and c["total"] == 8
    assert c["band"] == "run_heavy" and c["low_sample"] is False


def test_pass_heavy_cell_is_purple():
    c = _run_pass_matrix(_plays())["cells"]["3rd"]["Long"]
    assert c["band"] == "pass_heavy"
    assert c["pass"] == 5


def test_low_sample_cell_stays_grey():
    c = _run_pass_matrix(_plays())["cells"]["2nd"]["Short"]
    assert c["total"] == 2 and c["low_sample"] is True
    assert c["band"] == "none"
    assert c["run_pct"] == 50.0


def test_empty_cell_when_down_distance_absent():
    # 1st down had no Short-distance plays -> filled empty, not missing.
    c = _run_pass_matrix(_plays())["cells"]["1st"]["Short"]
    assert c["total"] == 0 and c["run_pct"] is None


def test_no_matrix_without_down_or_distance():
    assert _run_pass_matrix([_p("run", None, 10)]) == {}      # no down
    assert _run_pass_matrix([_p("run", 1, None)]) == {}       # no distance


def test_run_pass_band_ranges():
    assert run_pass_band(80)["band"] == "run_heavy"
    assert run_pass_band(65)["band"] == "run_lean"
    assert run_pass_band(50)["band"] == "balanced"
    assert run_pass_band(30)["band"] == "pass_lean"
    assert run_pass_band(15)["band"] == "pass_heavy"
    assert run_pass_band(None)["band"] == "none"
