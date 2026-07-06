"""
Event.player (migration 013) — the first-class player field.

Proves player-level tracking now works from the COLUMN alone (manual / live-logged
plays that set `player` but no extra_data.primary_player_jersey), and that the
older extra_data path still works (backward compatibility).

Run:  DATABASE_URL=... SECRET_KEY=... ANTHROPIC_API_KEY=... python -m backend.tests.test_event_player
"""
from types import SimpleNamespace

from backend.services.tendency_engine.players import analyze_players, _primary_jersey
from backend.services.report_export import build_export


def EV(player=None, extra=None, **cols):
    """A football play event. `player` is the first-class column; `extra` is extra_data."""
    base = dict(down=None, distance=None, field_position=None, hash_position=None,
                formation=None, personnel=None, play_type=None, motion=False,
                result=None, yards_gained=None, time_seconds=None,
                defensive_front=None, coverage=None, blitz=None, side="offense")
    base.update(cols)
    return SimpleNamespace(event_type="play", player=player, extra_data=extra or {}, **base)


def run():
    # ── _primary_jersey prefers the column, falls back to extra_data ─────────
    assert _primary_jersey(EV(player="22")) == "22"
    assert _primary_jersey(EV(player=None, extra={"primary_player_jersey": "7"})) == "7"
    assert _primary_jersey(EV(player="22", extra={"primary_player_jersey": "99"})) == "22", "column wins"
    assert _primary_jersey(EV()) is None
    print("  _primary_jersey column/fallback precedence ✓")

    # ── analyze_players tracks players from the COLUMN alone ─────────────────
    events = []
    for y in [4, 6, 12, 3, 5, 15, 2, 8]:      # RB #22, one big run
        events.append(EV(player="22", side="offense", play_type="run",
                         down=1, distance=10, yards_gained=y, result="gain"))
    for y in [9, 0, 22, 5]:                    # WR #7 targets
        events.append(EV(player="7", side="offense", play_type="pass",
                         down=3, distance=8, yards_gained=y, result="gain" if y else "incompletion"))

    pt = analyze_players(events, "football")
    assert pt["tracked"] is True, "should track players from the column"
    assert pt["players_identified"] == 2, f"expected 2 players, got {pt['players_identified']}"
    rb = pt["by_player"].get("offense#22")
    assert rb and rb["touches"] == 8 and rb["explosive_plays"] >= 1, f"RB card wrong: {rb}"
    print(f"  analyze_players from column: {list(pt['by_player'])} (RB touches={rb['touches']}, expl={rb['explosive_plays']}) ✓")

    # ── those feed Module-9 Player Bulletins ────────────────────────────────
    report = {"title": "Test", "sport": "football", "watermarked": False,
              "generated_at": None,
              "sections": [], "summary": {"player_tendencies": pt}}
    bulletins = build_export(report, "player")
    heads = [b["heading"] for b in bulletins["blocks"]]
    assert any(h.startswith("#22") for h in heads), f"expected a #22 bulletin, got {heads}"
    rb_block = next(b for b in bulletins["blocks"] if b["heading"].startswith("#22"))
    assert "big-play threat" in rb_block["body"], f"RB #22 should read as a big-play threat: {rb_block['body']}"
    print(f"  player bulletins from column: {heads} ✓")

    # ── backward compat: extra_data-only events still track ─────────────────
    legacy = [EV(player=None, extra={"primary_player_jersey": "5"}, side="offense",
                 play_type="run", down=1, distance=10, yards_gained=4, result="gain")
              for _ in range(5)]
    lp = analyze_players(legacy, "football")
    assert lp["tracked"] and "offense#5" in lp["by_player"], "legacy extra_data path must still work"
    print("  legacy extra_data path still tracked ✓")

    print("\nALL EVENT.PLAYER ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
