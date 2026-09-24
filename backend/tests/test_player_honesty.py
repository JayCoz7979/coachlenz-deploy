"""
Player grades / tendencies honesty (feature-value chart "Fix"): single-cam player
stats must not oversell thin data or miscount shots.

- Free throws are NOT field-goal attempts (excluded from a player's FG% / shot mix).
- "Left Wing 3" etc. count as threes (canonical zone taxonomy, not raw strings).
- A player with too few reps is flagged low_sample so the report treats them as
  directional, not fact.

Run:  python -m backend.tests.test_player_honesty
"""
from types import SimpleNamespace
from backend.services.tendency_engine.players import analyze_players, MIN_REPS


def EV(jersey, zone=None, stype=None, result=None, etype="shot", side="offense"):
    extra = {"primary_player_jersey": jersey}
    if zone:
        extra["shot_zone"] = zone
    if stype:
        extra["shot_type"] = stype
    return SimpleNamespace(event_type=etype, side=side, result=result, player=None,
                           extra_data=extra, yards_gained=None, play_type=None,
                           down=None, distance=None)


def test_free_throws_excluded_wing_three_counted_low_sample_flagged():
    ev = [
        # #5: one made wing 3 (a real FGA + a three) plus two free throws (NOT FGA)
        EV("5", zone="Left Wing 3", stype="Pull-Up Jumper", result="made"),
        EV("5", zone="Free Throw Line", stype="Free Throw", result="made"),
        EV("5", zone="Free Throw Line", stype="Free Throw", result="missed"),
    ]
    out = analyze_players(ev, "basketball")
    p5 = out["by_player"]["offense#5"]
    assert p5["shot_attempts"] == 1, f"free throws must be excluded from FGA: {p5}"
    assert p5["fg_pct"] == 100.0, f"1/1 field goals: {p5}"
    assert p5["three_attempts"] == 1, f"wing 3 must count as a three: {p5}"
    assert p5["low_sample"] is True, "3 reps is below MIN_REPS -> directional"

    # A player with enough field goals is NOT low_sample.
    ev2 = [EV("3", zone="Restricted Area", stype="Layup", result="made") for _ in range(MIN_REPS)]
    out2 = analyze_players(ev2, "basketball")
    p3 = out2["by_player"]["offense#3"]
    assert p3["shot_attempts"] == MIN_REPS
    assert p3["low_sample"] is False
    assert out2["low_sample_count"] == 0


def run():
    test_free_throws_excluded_wing_three_counted_low_sample_flagged()
    print("ALL PLAYER-HONESTY ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
