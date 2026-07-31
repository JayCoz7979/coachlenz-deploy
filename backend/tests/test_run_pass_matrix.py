"""
§12 Map 4 — Run/Pass tendency matrix (Down x Hash, cell = run%, 5-band color).
"""
from types import SimpleNamespace

from backend.services.tendency_engine.football import _run_pass_matrix
from backend.services.heatmap import run_pass_band


def _p(kind, down, hsh):
    return SimpleNamespace(event_type=kind, play_type=None, down=down, distance=10,
                           hash_position=hsh, yards_gained=None, side="offense")


def _plays():
    plays = []
    # 1st & Left: 6 run / 2 pass -> 75% run -> RED
    plays += [_p("run", 1, "Left")] * 6 + [_p("pass", 1, "Left")] * 2
    # 3rd & Right: 1 run / 5 pass -> ~17% run -> PURPLE (pass heavy)
    plays += [_p("run", 3, "Right")] * 1 + [_p("pass", 3, "Right")] * 5
    # 2nd & Middle: 1 run / 1 pass -> total 2 < 4 -> low sample, grey
    plays += [_p("run", 2, "Middle"), _p("pass", 2, "Middle")]
    return plays


def test_matrix_shape_and_ordering():
    m = _run_pass_matrix(_plays())
    assert m["rows"] == ["1st", "2nd", "3rd"]
    assert m["cols"] == ["Left", "Middle", "Right"]   # canonical hash order
    assert m["min_sample"] == 4


def test_run_heavy_cell_is_red():
    c = _run_pass_matrix(_plays())["cells"]["1st"]["Left"]
    assert c["run_pct"] == 75.0 and c["run"] == 6 and c["total"] == 8
    assert c["band"] == "run_heavy" and c["low_sample"] is False


def test_pass_heavy_cell_is_purple():
    c = _run_pass_matrix(_plays())["cells"]["3rd"]["Right"]
    assert c["band"] == "pass_heavy"
    assert c["pass"] == 5


def test_low_sample_cell_stays_grey():
    c = _run_pass_matrix(_plays())["cells"]["2nd"]["Middle"]
    assert c["total"] == 2 and c["low_sample"] is True
    assert c["band"] == "none"          # not called as a tendency
    assert c["run_pct"] == 50.0         # number still available


def test_empty_cell_when_down_hash_absent():
    # 1st down had no Right-hash plays -> filled empty, not missing.
    c = _run_pass_matrix(_plays())["cells"]["1st"]["Right"]
    assert c["total"] == 0 and c["run_pct"] is None


def test_no_matrix_without_down_or_hash():
    assert _run_pass_matrix([_p("run", None, None)]) == {}


def test_run_pass_band_ranges():
    assert run_pass_band(80)["band"] == "run_heavy"
    assert run_pass_band(65)["band"] == "run_lean"
    assert run_pass_band(50)["band"] == "balanced"
    assert run_pass_band(30)["band"] == "pass_lean"
    assert run_pass_band(15)["band"] == "pass_heavy"
    assert run_pass_band(None)["band"] == "none"
