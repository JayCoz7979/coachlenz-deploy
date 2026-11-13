"""
Pure-logic tests for the FOOTBALL scoreboard score-delta reconciler. No DB, no network,
no model call: these prove the scoring attribution, missed-kick, phantom-touchdown,
and synthesis logic against synthetic score timelines, so the behavior is validated
without a paid analysis run.
"""
from backend.services import football_score_reconcile as FR


def _read(t, home, away, conf=1.0):
    return {"t": t, "home": home, "away": away, "conf": conf}


def _play(t, result=None, play_type=None, st_unit=None, conf=0.6, side="offense",
          kick_result=None):
    p = {"time_seconds": t, "result": result, "play_type": play_type,
         "st_unit": st_unit, "confidence": conf, "side": side}
    if kick_result is not None:
        p["kick_result"] = kick_result
    return p


# ── timeline primitives ─────────────────────────────────────────────────────

def test_confirmed_totals_need_two_agreeing_reads():
    reads = [_read(5, 0, 0), _read(8, 0, 0), _read(13, 7, 0), _read(16, 7, 0)]
    assert FR.confirmed_totals(reads) == [(5, 0), (13, 7)]


def test_single_frame_misread_is_debounced():
    reads = [_read(5, 7, 0), _read(8, 7, 0), _read(12, 99, 0),
             _read(15, 14, 0), _read(18, 14, 0)]
    conf = FR.confirmed_totals(reads)
    assert conf == [(5, 7), (15, 14)]


def test_low_confidence_reads_dropped():
    reads = [_read(5, 0, 0), _read(8, 0, 0), _read(12, 6, 0, conf=0.3),
             _read(15, 6, 0), _read(18, 6, 0)]
    # the 0.3 read is dropped; 6 still confirms on the two good reads
    assert FR.confirmed_totals(reads) == [(5, 0), (15, 6)]


def test_scoring_events_each_football_delta():
    # +6 TD, +3 FG, +1 PAT, +2 safety (no preceding TD)
    conf = [(0, 0), (10, 6), (20, 9), (30, 10), (120, 12)]
    evs = FR.scoring_events(conf)
    kinds = [(e["points"], e["kind"]) for e in evs]
    assert kinds == [(6, "touchdown"), (3, "field_goal"), (1, "pat"), (2, "safety")]


def test_scoring_events_skip_illegal_jumps_and_decreases():
    conf = [(0, 10), (5, 9), (10, 14), (20, 60), (30, 63)]
    # 10->9 skip (decrease), 9->14 is +5 skip (illegal), 14->60 skip (>8), 60->63 is +3
    assert [(e["points"], e["kind"]) for e in FR.scoring_events(conf)] == [(3, "field_goal")]


def test_compound_seven_decomposes_to_td_then_pat():
    conf = [(0, 0), (100, 7)]
    evs = FR.scoring_events(conf)
    assert [(e["points"], e["kind"], e["order"]) for e in evs] == [
        (6, "touchdown", 0), (1, "pat", 1)]
    assert all(e["t"] == 100 for e in evs)


def test_compound_eight_decomposes_to_td_then_two_point():
    conf = [(0, 0), (100, 8)]
    assert [(e["points"], e["kind"]) for e in FR.scoring_events(conf)] == [
        (6, "touchdown"), (2, "two_point")]


def test_two_point_vs_safety_context():
    # +2 shortly after a +6 TD is a two-point try
    conf = [(0, 0), (40, 6), (55, 8)]
    evs = FR.scoring_events(conf)
    assert [(e["points"], e["kind"]) for e in evs] == [(6, "touchdown"), (2, "two_point")]
    # +2 with no recent TD (gap > TWO_PT_GAP) is a safety
    conf2 = [(0, 0), (40, 6), (400, 8)]
    evs2 = FR.scoring_events(conf2)
    assert [(e["points"], e["kind"]) for e in evs2] == [(6, "touchdown"), (2, "safety")]


# ── result locking (strict map) ─────────────────────────────────────────────

def test_touchdown_locks_most_recent_play():
    plays = [_play(95, result="Gain")]
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["touchdowns_set"] == 1
    assert plays[0]["result"] == "Touchdown"
    assert plays[0]["result_source"] == "scoreboard"
    assert plays[0]["result_verified"] is True
    assert plays[0]["points"] == 6
    assert plays[0]["scoring_type"] == "Touchdown"
    # a strict, board-definitive touchdown does not demand review
    assert plays[0].get("needs_review") is not True


def test_field_goal_locks_made():
    plays = [_play(96, play_type="Field Goal", result=None)]
    reads = [_read(90, 7, 0), _read(93, 7, 0), _read(100, 10, 0), _read(104, 10, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["field_goals_set"] == 1
    assert plays[0]["result"] == "Made"
    assert plays[0]["points"] == 3
    assert plays[0]["scoring_type"] == "Field Goal"


def test_compound_td_and_pat_map_to_their_own_snaps():
    td = _play(100, result="Gain")
    pat = _play(108, play_type="PAT")
    plays = [td, pat]
    reads = [_read(95, 0, 0), _read(98, 0, 0), _read(110, 7, 0), _read(113, 7, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["touchdowns_set"] == 1 and stats["pats_set"] == 1
    # the later snap (PAT) takes the +1, the earlier snap takes the +6 touchdown
    assert td["result"] == "Touchdown" and td["points"] == 6
    assert pat["result"] == "Made" and pat["points"] == 1
    assert pat["scoring_type"] == "PAT"


def test_pat_without_detected_kick_snap_synthesizes_not_steals_the_td():
    # +7 but only the touchdown run was detected (the extra-point kick snap was missed).
    # The PAT must NOT be stamped onto the TD run; the run stays the touchdown and the PAT
    # is synthesized.
    run = _play(100, result="Gain", play_type="Run")
    plays = [run]
    reads = [_read(95, 0, 0), _read(98, 0, 0), _read(112, 7, 0), _read(116, 7, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert run["result"] == "Touchdown" and run["points"] == 6
    assert stats["touchdowns_set"] == 1 and stats["pats_set"] == 0
    synth = [p for p in out if p.get("synthesized")]
    assert len(synth) == 1 and synth[0]["scoring_type"] == "PAT"


# ── relaxed window + affinity ────────────────────────────────────────────────

def test_relaxed_maps_only_a_play_with_scoring_affinity():
    # FG attempt 28s before the delta: inside relaxed (40) but outside strict (15).
    fg = _play(72, play_type="Field Goal")
    plays = [fg]
    reads = [_read(65, 14, 0), _read(68, 14, 0), _read(100, 17, 0), _read(104, 17, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["field_goals_set"] == 1 and stats["relaxed_mapped"] == 1
    assert fg["result"] == "Made"
    # a relaxed (less certain) map asks for the coach's eyes
    assert fg["needs_review"] is True


def test_relaxed_will_not_crown_a_generic_earlier_snap():
    # only play is an ordinary run 28s before the delta, NO scoring affinity.
    run = _play(72, result="Gain", play_type="Run")
    plays = [run]
    reads = [_read(65, 0, 0), _read(68, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads)
    # the run is left untouched; the unmapped touchdown is synthesized instead
    assert run["result"] == "Gain"
    assert "result_source" not in run
    assert stats["synthesized"] == 1
    synth = [p for p in out if p.get("synthesized")]
    assert len(synth) == 1 and synth[0]["scoring_type"] == "Touchdown"


# ── synthesis ────────────────────────────────────────────────────────────────

def test_unmapped_score_is_synthesized_blank_and_flagged():
    plays = []
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["synthesized"] == 1
    s = out[0]
    assert s["result"] == "Touchdown" and s["synthesized"] is True
    assert s["needs_review"] is True and s["result_source"] == "scoreboard_synthesized"
    # nothing invented: no side, no play_type, no scorer
    assert "side" not in s and "play_type" not in s


def test_synthesis_can_be_disabled():
    plays = []
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads, synthesize=False)
    assert stats["synthesized"] == 0 and stats["unclear_points"] == 1
    assert out == []


def test_safety_synthesis_has_no_made_result():
    plays = []
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(200, 2, 0), _read(204, 2, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["safeties_set"] == 0 and stats["synthesized"] == 1
    s = out[0]
    assert s["scoring_type"] == "Safety"
    # safety has no clean 'Made' result enum, so we do not force one
    assert "result" not in s


# ── missed kick (positive evidence only) ─────────────────────────────────────

def test_missed_field_goal_on_flat_board():
    fg = _play(50, play_type="Field Goal", result=None)
    plays = [fg]
    reads = [_read(40, 7, 0), _read(44, 7, 0), _read(58, 7, 0), _read(64, 7, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["missed_kicks_set"] == 1
    assert fg["result"] == "Missed"
    assert fg["result_source"] == "scoreboard"


def test_kick_not_touched_without_evidence():
    # board unreadable after the attempt -> leave the kick exactly as the model left it
    fg = _play(50, play_type="Field Goal", result=None)
    plays = [fg]
    reads = [_read(40, 7, 0), _read(44, 7, 0)]  # nothing after the attempt
    out, stats = FR.reconcile(plays, reads)
    assert stats["missed_kicks_set"] == 0
    assert fg["result"] is None and "result_source" not in fg


# ── phantom touchdown downgrade ──────────────────────────────────────────────

def test_phantom_touchdown_downgraded_on_flat_board():
    td = _play(50, result="Touchdown", play_type="Run")
    plays = [td]
    reads = [_read(40, 14, 0), _read(44, 14, 0), _read(58, 14, 0), _read(64, 14, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["phantom_td_fixed"] == 1
    assert td["result"] == "Gain"
    assert td["scoreboard_contradicted"] is True
    assert td["needs_review"] is True


def test_real_touchdown_is_not_downgraded():
    # the board DOES credit +6, so the touchdown stands (it is mapped, not contradicted)
    td = _play(50, result="Touchdown", play_type="Run")
    plays = [td]
    reads = [_read(40, 8, 0), _read(44, 8, 0), _read(56, 14, 0), _read(60, 14, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert stats["phantom_td_fixed"] == 0 and stats["touchdowns_set"] == 1
    assert td["result"] == "Touchdown" and td.get("scoreboard_contradicted") is not True


# ── guards ───────────────────────────────────────────────────────────────────

def test_disabled_changes_nothing():
    td = _play(95, result="Gain")
    plays = [td]
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads, enabled=False)
    assert td["result"] == "Gain" and stats["touchdowns_set"] == 0


def test_no_scoreboard_changes_nothing():
    td = _play(95, result="Gain")
    plays = [td]
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads, has_scoreboard=False)
    assert td["result"] == "Gain" and stats["deltas_accepted"] == 0


def test_no_reads_leaves_everything_untouched():
    run = _play(50, result="Gain", play_type="Run")
    plays = [run]
    out, stats = FR.reconcile(plays, [])
    assert run["result"] == "Gain" and "result_source" not in run
    assert stats["deltas_accepted"] == 0


def test_ordinary_play_with_no_score_change_is_left_alone():
    # a normal run, board flat around it, is neither a kick nor a phantom TD -> untouched
    run = _play(50, result="Gain", play_type="Run")
    plays = [run]
    reads = [_read(40, 10, 0), _read(44, 10, 0), _read(58, 10, 0), _read(64, 10, 0)]
    out, stats = FR.reconcile(plays, reads)
    assert run["result"] == "Gain" and "result_source" not in run
    assert stats["missed_kicks_set"] == 0 and stats["phantom_td_fixed"] == 0


def test_play_without_timestamp_is_ignored_safely():
    plays = [{"result": "Gain"}]  # no time_seconds
    reads = [_read(90, 0, 0), _read(93, 0, 0), _read(100, 6, 0), _read(104, 6, 0)]
    out, stats = FR.reconcile(plays, reads)
    # the timeless play is untouched; the score still synthesizes
    assert plays[0]["result"] == "Gain"
    assert stats["synthesized"] == 1
