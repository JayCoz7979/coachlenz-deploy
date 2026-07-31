"""
§12 Map 3 — Turnover cluster map (basketball).

Single-camera film has no court coordinates for turnovers, so this clusters by the
real how/where signal (transition vs the half-court action) and flags the dominant
cluster as the "force them here" — no fabricated positions.
"""
from types import SimpleNamespace

from backend.services.tendency_engine.basketball import _turnover_map, _turnover_cluster_label


def _to(**extra):
    return SimpleNamespace(event_type="turnover", play_type=None, extra_data=extra)


# ── cluster labels ───────────────────────────────────────────────────────────
def test_cluster_labels():
    assert _turnover_cluster_label(_to(possession_origin="transition")) == "Transition"
    assert _turnover_cluster_label(_to(transition_type="run-out")) == "Transition"
    assert _turnover_cluster_label(_to(play_action="Pick and Roll")) == "Ball screens"
    assert _turnover_cluster_label(_to(play_action="Isolation")) == "One-on-one"
    assert _turnover_cluster_label(_to(play_action="Flex Cut")) == "Flex Cut"   # passthrough
    assert _turnover_cluster_label(_to()) == "Half-court sets"


# ── map + force-here flag ────────────────────────────────────────────────────
def test_dominant_cluster_flagged_force_here():
    tos = [_to(possession_origin="transition")] * 3 + [_to(play_action="Isolation")] * 2
    m = _turnover_map(tos)
    assert m["total"] == 5
    assert m["top_cluster"] == "Transition"
    assert m["zones"][0] == {"zone": "Transition", "count": 3, "pct": 60.0}
    assert m["force_here"] and "transition" in m["force_here"]


def test_thin_sample_has_no_force_here():
    m = _turnover_map([_to(possession_origin="transition")] * 2)   # total 2 < 5
    assert m["top_cluster"] == "Transition"     # still shown, informational
    assert m["force_here"] is None              # not enough to prescribe


def test_no_dominant_when_top_cluster_too_small():
    # 5 turnovers but spread thin (max cluster = 2) -> no force-here.
    tos = ([_to(play_action="Isolation")] * 2 + [_to(play_action="Post Up")] * 2
           + [_to(possession_origin="transition")])
    m = _turnover_map(tos)
    assert m["total"] == 5 and m["force_here"] is None


def test_empty():
    assert _turnover_map([]) == {}
