"""
Coach-flagged-plays digest for the report (pure, no DB). Only starred/annotated
plays are collected, chronological, capped, with a compact tag + verbatim note.
"""
from types import SimpleNamespace

from backend.services.coach_notes import collect_flagged_plays, _play_tag, _clock


def _ev(**kw):
    base = dict(event_type="play", time_seconds=None, down=None, distance=None,
                formation=None, play_type=None, coverage=None, result=None,
                yards_gained=None, player=None, is_highlight=False, coach_note=None,
                extra_data={})
    base.update(kw)
    return SimpleNamespace(**base)


def test_only_starred_or_noted_plays_are_collected():
    events = [
        _ev(time_seconds=10, is_highlight=True),
        _ev(time_seconds=20, coach_note="watch the pull guard"),
        _ev(time_seconds=30),  # neither flagged nor noted -> skipped
    ]
    out = collect_flagged_plays(events)
    assert len(out) == 2
    assert {o["clock"] for o in out} == {"0:10", "0:20"}


def test_note_is_verbatim_and_highlight_flagged():
    out = collect_flagged_plays([_ev(time_seconds=65, is_highlight=True, coach_note="great read by #7")])
    assert out[0]["note"] == "great read by #7"
    assert out[0]["is_highlight"] is True
    assert out[0]["clock"] == "1:05"


def test_chronological_order_untimed_last():
    events = [
        _ev(time_seconds=50, coach_note="c"),
        _ev(time_seconds=None, is_highlight=True),
        _ev(time_seconds=5, coach_note="a"),
    ]
    out = collect_flagged_plays(events)
    assert [o["clock"] for o in out] == ["0:05", "0:50", "--"]
    assert "time_seconds" not in out[0]  # internal sort key stripped from output


def test_scout_meta_rows_skipped():
    out = collect_flagged_plays([_ev(event_type="scout_meta", is_highlight=True, coach_note="x")])
    assert out == []


def test_limit_keeps_earliest():
    events = [_ev(time_seconds=i, is_highlight=True) for i in range(100)]
    out = collect_flagged_plays(events, limit=10)
    assert len(out) == 10
    assert out[0]["clock"] == "0:00" and out[-1]["clock"] == "0:09"


def test_blank_note_still_collected_when_highlighted():
    out = collect_flagged_plays([_ev(time_seconds=1, is_highlight=True, coach_note="   ")])
    assert len(out) == 1 and out[0]["note"] == ""


def test_play_tag_football_descriptor():
    tag = _play_tag(_ev(down=3, distance=7, formation="Trips", play_type="Pass",
                        result="Gain", yards_gained=12, player="7"))
    assert tag == "3&7 · Trips · Pass · Gain · +12 yds · #7"


def test_play_tag_basketball_from_extra_data():
    tag = _play_tag(_ev(event_type="shot", result="made", player="4",
                        extra_data={"shot_zone": "Left Corner 3"}))
    assert "shot" in tag and "Left Corner 3" in tag and "made" in tag and "#4" in tag


def test_clock_formats_and_guards():
    assert _clock(0) == "0:00"
    assert _clock(125) == "2:05"
    assert _clock(None) == "--"
