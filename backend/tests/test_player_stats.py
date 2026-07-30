"""
Per-player season stat aggregation (pure, no DB). Uses SimpleNamespace as an
Event stand-in — the service reads only attribute/`extra_data` shape.
"""
from types import SimpleNamespace

from backend.services.player_stats import (
    aggregate_player_stats,
    stat_line_for,
    top_play_types,
)


def _ev(game_id="g1", player=None, play_type=None, yards=None, players=None, event_type="play"):
    return SimpleNamespace(
        game_id=game_id, player=player, play_type=play_type, yards_gained=yards,
        event_type=event_type, extra_data={"players": players or []},
    )


def test_primary_actor_counts_plays_yards_and_type():
    agg = aggregate_player_stats([
        _ev(player="7", play_type="Run", yards=8),
        _ev(player="7", play_type="Run", yards=-2),
        _ev(player="7", play_type="Pass", yards=15),
    ])
    s = agg["7"]
    assert s["primary_plays"] == 3
    assert s["plays"] == 3
    assert s["total_yards"] == 21  # 8 - 2 + 15
    assert s["by_play_type"] == {"Run": 2, "Pass": 1}
    assert s["games"] == 1


def test_cast_players_get_roles_and_play_involvement():
    agg = aggregate_player_stats([
        _ev(player="7", play_type="Pass", yards=12,
            players=[{"jersey": "7", "role": "passer"}, {"jersey": "80", "role": "receiver"}]),
    ])
    # #80 is in the cast only: one play, a receiver role, no primary plays / yards.
    assert agg["80"]["plays"] == 1
    assert agg["80"]["primary_plays"] == 0
    assert agg["80"]["total_yards"] == 0
    assert agg["80"]["by_role"] == {"receiver": 1}
    # #7 is both primary and in the cast — the play counts once toward plays.
    assert agg["7"]["plays"] == 1
    assert agg["7"]["primary_plays"] == 1
    assert agg["7"]["by_role"] == {"passer": 1}


def test_distinct_games_are_counted_once():
    agg = aggregate_player_stats([
        _ev(game_id="g1", player="10"),
        _ev(game_id="g1", player="10"),
        _ev(game_id="g2", player="10"),
    ])
    assert agg["10"]["games"] == 2
    assert agg["10"]["plays"] == 3


def test_jersey_normalization_merges_leading_zero():
    agg = aggregate_player_stats([
        _ev(player="07", play_type="Run", yards=3),
        _ev(player="7", play_type="Run", yards=4),
    ])
    assert set(agg.keys()) == {"7"}
    assert agg["7"]["primary_plays"] == 2
    assert agg["7"]["total_yards"] == 7


def test_scout_meta_rows_are_ignored():
    agg = aggregate_player_stats([
        _ev(player="5", event_type="scout_meta", yards=99),
        _ev(player="5", play_type="Run", yards=6),
    ])
    assert agg["5"]["plays"] == 1
    assert agg["5"]["total_yards"] == 6


def test_boolean_yards_not_summed():
    # yards_gained should never be a bool, but guard against True==1 slipping in.
    agg = aggregate_player_stats([_ev(player="9", play_type="Run", yards=True)])
    assert agg["9"]["total_yards"] == 0


def test_stat_line_for_missing_jersey_is_zeroed():
    line = stat_line_for([_ev(player="1")], jersey="99")
    assert line == {"plays": 0, "primary_plays": 0, "total_yards": 0,
                    "games": 0, "by_play_type": {}, "by_role": {}}
    assert "_games" not in line


def test_top_play_types_ranks_and_limits():
    line = {"by_play_type": {"Run": 24, "Pass": 11, "Screen": 3, "Trick": 1}}
    tops = top_play_types(line, limit=2)
    assert tops == [{"play_type": "Run", "count": 24}, {"play_type": "Pass", "count": 11}]


def test_empty_events_yield_no_stats():
    assert aggregate_player_stats([]) == {}
