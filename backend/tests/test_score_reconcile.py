"""
Pure-logic tests for the basketball scoreboard score-delta reconciler. No DB, no network,
no model call: these prove the make/miss and free-throw labeling logic against synthetic
score timelines, so the fix is validated without a paid analysis run.
"""
from backend.services import score_reconcile as SR


def _read(t, home, away, conf=1.0, clock=None):
    return {"t": t, "home": home, "away": away, "conf": conf, "clock_running": clock}


def _shot(t, zone=None, stype=None, result=None, conf=0.6, etype="shot"):
    return {"event_type": etype, "time_seconds": t, "shot_zone": zone,
            "shot_type": stype, "result": result, "confidence": conf}


# ── timeline primitives ─────────────────────────────────────────────────────

def test_confirmed_totals_need_two_agreeing_reads():
    reads = [_read(5, 5, 5), _read(8, 5, 5), _read(13, 7, 5), _read(16, 7, 5)]
    assert SR.confirmed_totals(reads) == [(5, 10), (13, 12)]


def test_single_frame_misread_is_debounced():
    # a lone 99 between stable 10 and stable 12 must never become an event
    reads = [_read(5, 5, 5), _read(8, 5, 5), _read(12, 90, 9),
             _read(15, 7, 5), _read(18, 7, 5)]
    conf = SR.confirmed_totals(reads)
    assert conf == [(5, 10), (15, 12)]
    assert SR.scoring_events(conf) == [{"t": 15, "points": 2}]


def test_scoring_events_skip_non_monotonic_and_big_jumps():
    conf = [(0, 10), (5, 9), (10, 12), (20, 40), (30, 43)]
    # 10->9 skip, 9->12 is +3, 12->40 skip (>3), 40->43 is +3
    assert SR.scoring_events(conf) == [{"t": 10, "points": 3}, {"t": 30, "points": 3}]


def test_low_confidence_reads_dropped():
    reads = [_read(5, 5, 5, conf=0.2), _read(8, 5, 5, conf=0.2)]
    assert SR.confirmed_totals(reads) == []


# ── make / miss / type ───────────────────────────────────────────────────────

def test_made_two_maps_to_prior_layup():
    shot = _shot(10, zone="Restricted Area", stype="Layup", result=None)
    reads = [_read(5, 5, 5), _read(8, 5, 5), _read(13, 7, 5), _read(16, 7, 5)]
    plays, stats = SR.reconcile([shot], reads)
    assert shot["result"] == "Made"
    assert shot["points"] == 2
    assert shot["result_source"] == "scoreboard"
    assert shot["confidence"] >= SR.SCOREBOARD_CONF
    assert stats["made_set"] == 1


def test_plus_one_forces_free_throw_label():
    # a free throw mislabeled as a layup, confirmed by a +1 on the board
    shot = _shot(20, zone="Free Throw Line", stype="Layup", result=None, conf=0.5)
    reads = [_read(14, 6, 6, clock=False), _read(17, 6, 6, clock=False),
             _read(22, 7, 6, clock=False), _read(24, 7, 6, clock=False)]
    plays, stats = SR.reconcile([shot], reads)
    assert shot["result"] == "Made"
    assert shot["points"] == 1
    assert shot["shot_type"] == "Free Throw"
    assert stats["ft_type_fixed"] == 1   # type fixed before the score mapping too


def test_made_three_sets_three_pointer_when_zone_is_a_three():
    shot = _shot(30, zone="Left Wing 3", stype="Catch and Shoot", result=None)
    reads = [_read(24, 10, 8), _read(26, 10, 8), _read(33, 13, 8), _read(35, 13, 8)]
    plays, stats = SR.reconcile([shot], reads)
    assert shot["result"] == "Made"
    assert shot["points"] == 3
    assert shot["shot_type"] == "3-Pointer"


def test_free_throw_pair_maps_two_distinct_shots():
    s1 = _shot(40, zone="Free Throw Line", stype="Free Throw", result=None)
    s2 = _shot(43, zone="Free Throw Line", stype="Free Throw", result=None)
    reads = [_read(38, 10, 10, clock=False), _read(39, 10, 10, clock=False),
             _read(45, 11, 10, clock=False), _read(46, 11, 10, clock=False),
             _read(48, 12, 10, clock=False), _read(49, 12, 10, clock=False)]
    plays, stats = SR.reconcile([s1, s2], reads)
    assert s1["result"] == "Made" and s2["result"] == "Made"
    assert stats["made_set"] == 2


def test_and_one_flags_the_bonus_free_throw():
    fg = _shot(60, zone="Restricted Area", stype="Layup", result=None)
    ft = _shot(66, zone="Free Throw Line", stype="Free Throw", result=None)
    reads = [_read(55, 20, 18), _read(57, 20, 18),       # total 38
             _read(63, 22, 18), _read(64, 22, 18),       # +2 -> 40  (the layup)
             _read(69, 23, 18), _read(70, 23, 18)]       # +1 -> 41  (the and-1 FT)
    plays, stats = SR.reconcile([fg, ft], reads)
    assert fg["result"] == "Made" and fg["points"] == 2
    assert ft["result"] == "Made" and ft["points"] == 1
    assert ft.get("and_one") is True
    assert stats["and_one"] == 1


def test_miss_only_on_positive_evidence():
    shot = _shot(80, zone="Mid-Range Center", stype="Pull-Up Jumper", result=None)
    reads = [_read(74, 20, 20), _read(76, 20, 20),       # total 40 before
             _read(83, 20, 20), _read(86, 20, 20)]       # still 40 after -> miss
    plays, stats = SR.reconcile([shot], reads)
    assert shot["result"] == "Missed"
    assert shot["result_source"] == "scoreboard"
    assert stats["missed_set"] == 1


def test_unreadable_after_leaves_shot_null():
    shot = _shot(100, zone="Mid-Range Center", stype="Pull-Up Jumper", result=None)
    reads = [_read(90, 30, 28), _read(92, 30, 28)]       # nothing readable after the shot
    plays, stats = SR.reconcile([shot], reads)
    assert shot["result"] is None                         # never guessed
    assert stats["left_null"] == 1


def test_ft_type_fix_without_any_score_reads():
    # stopped clock + free-throw line = free throw, even with no score change available
    shot = _shot(50, zone="Free Throw Line", stype="Layup", result="Made")
    reads = [_read(48, 9, 9, clock=False), _read(52, 9, 9, clock=False)]
    plays, stats = SR.reconcile([shot], reads)
    assert shot["shot_type"] == "Free Throw"
    assert stats["ft_type_fixed"] == 1
    assert shot["result"] == "Made"                       # result untouched (no delta)


def test_no_scoreboard_changes_nothing():
    shot = _shot(10, zone="Restricted Area", stype="Layup", result=None)
    reads = [_read(5, 5, 5), _read(8, 5, 5), _read(13, 7, 5), _read(16, 7, 5)]
    plays, stats = SR.reconcile([shot], reads, has_scoreboard=False)
    assert shot["result"] is None
    assert stats == {"deltas_accepted": 0, "made_set": 0, "missed_set": 0,
                     "ft_type_fixed": 0, "and_one": 0, "left_null": 0}


def test_disabled_changes_nothing():
    shot = _shot(10, zone="Restricted Area", stype="Layup", result=None)
    reads = [_read(5, 5, 5), _read(8, 5, 5), _read(13, 7, 5), _read(16, 7, 5)]
    _, stats = SR.reconcile([shot], reads, enabled=False)
    assert shot["result"] is None
    assert stats["made_set"] == 0


def test_non_shot_events_are_ignored():
    reb = _shot(10, result=None, etype="rebound")
    reads = [_read(5, 5, 5), _read(8, 5, 5), _read(13, 7, 5), _read(16, 7, 5)]
    _, stats = SR.reconcile([reb], reads)
    assert reb["result"] is None
    assert stats["made_set"] == 0


# ── dedicated scoreboard-timeline planner ────────────────────────────────────

def _frames(times):
    return [(f"f_{t}.jpg", float(t)) for t in times]


def test_plan_timeline_samples_by_cadence():
    # frames every 1s for 20s, cadence 5 -> keep ~one per 5s (0,5,10,15,20)
    frames = _frames(range(0, 21))
    batches, picked = SR.plan_timeline_batches(frames, cadence=5.0, bsz=6, max_calls=180)
    assert picked == 5
    kept_times = [t for b in batches for (_p, t) in b]
    assert kept_times == [0.0, 5.0, 10.0, 15.0, 20.0]


def test_plan_timeline_batches_split_by_size():
    frames = _frames(range(0, 100, 5))   # 20 frames, 5s apart, cadence 5 keeps all 20
    batches, picked = SR.plan_timeline_batches(frames, cadence=5.0, bsz=6, max_calls=180)
    assert picked == 20
    assert [len(b) for b in batches] == [6, 6, 6, 2]


def test_plan_timeline_hard_caps_calls_but_keeps_coverage():
    frames = _frames(range(0, 6000, 5))   # a long game: ~1200 reads
    batches, picked = SR.plan_timeline_batches(frames, cadence=5.0, bsz=6, max_calls=50)
    assert len(batches) == 50               # never exceeds the cap
    # coverage spans start to end of the game, not just the opening
    first_t = batches[0][0][1]
    last_t = batches[-1][-1][1]
    assert first_t < 100 and last_t > 5000


def test_plan_timeline_empty_is_safe():
    assert SR.plan_timeline_batches([], cadence=5.0, bsz=6, max_calls=180) == ([], 0)
