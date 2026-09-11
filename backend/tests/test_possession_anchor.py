"""
Basketball possession anchor. Locks the deterministic coach-set path (the fix for
offense/defense flipping) and the auto-anchor fallback.
"""
from backend.services.possession_anchor import anchor_sides


def _p(direction, side, quarter, event_type="shot"):
    return {"attack_direction": direction, "side": side, "quarter": quarter, "event_type": event_type}


def test_coach_dir_is_deterministic_and_flips_at_half():
    # Coach: scouted team attacks LEFT in H1 -> left=offense in H1, right=offense in H2.
    plays = [
        _p("left", "defense", 1),   # wrong: attacking left in H1 = offense -> corrected
        _p("right", "offense", 1),  # wrong: right in H1 = defense -> corrected
        _p("right", "defense", 3),  # H2: right = offense -> corrected
        _p("left", "offense", 4),   # H2: left = defense -> corrected
    ]
    out, changed = anchor_sides(plays, scout_attack_dir_h1="left")
    assert [p["side"] for p in out] == ["offense", "defense", "offense", "defense"]
    assert changed == 4


def test_coach_dir_leaves_correct_reads_untouched():
    plays = [_p("left", "offense", 1), _p("right", "defense", 2)]
    out, changed = anchor_sides(plays, scout_attack_dir_h1="left")
    assert changed == 0
    assert [p["side"] for p in out] == ["offense", "defense"]


def test_timeouts_and_transition_are_not_touched():
    plays = [_p("left", "timeout", 1, "timeout"), _p("right", "transition", 1, "shot")]
    out, changed = anchor_sides(plays, scout_attack_dir_h1="left")
    assert changed == 0
    assert out[0]["side"] == "timeout" and out[1]["side"] == "transition"


def test_auto_anchor_makes_a_half_consistent():
    # No coach dir. Model mostly says left=offense in H1 (3 of 4), one contradicts.
    plays = [
        _p("left", "offense", 1), _p("left", "offense", 1), _p("left", "offense", 1),
        _p("left", "defense", 1),   # the odd one out -> corrected to offense
        _p("right", "offense", 1),  # right in H1 -> should become defense
    ]
    out, changed = anchor_sides(plays, scout_attack_dir_h1=None)
    assert [p["side"] for p in out[:4]] == ["offense"] * 4  # all left = offense
    assert out[4]["side"] == "defense"                      # right = defense
    assert changed == 2


def test_auto_anchor_second_half_is_opposite_when_only_h1_seen():
    plays = [
        _p("left", "offense", 1), _p("left", "offense", 1),
        _p("left", "defense", 3),  # H2: left should be DEFENSE (H1 offense was left) -> unchanged
        _p("right", "offense", 3), # H2: right should be OFFENSE -> unchanged
    ]
    out, _ = anchor_sides(plays, scout_attack_dir_h1=None)
    assert out[2]["side"] == "defense"
    assert out[3]["side"] == "offense"


def test_normalizes_screen_left_wording_and_ignores_unknown_direction():
    plays = [_p("Screen Left", "defense", 1), _p(None, "defense", 1)]
    out, changed = anchor_sides(plays, scout_attack_dir_h1="left")
    assert out[0]["side"] == "offense"   # "Screen Left" -> left -> offense
    assert out[1]["side"] == "defense"   # no direction -> left untouched
    assert changed == 1
