"""
Deterministic tests for the EAGLE EYE jersey reader's merge + legality logic
(the parts that don't need ffmpeg or the vision API). Crop geometry and vision
quality are validated on real film, not here.

Run:  python -m backend.tests.test_jersey_reader
"""
from backend.workers.worker_ai_detect import AiDetectWorker

w = AiDetectWorker()
passed, failed = 0, 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {label}")
    else:
        failed += 1; print(f"  FAIL  {label}")


def run():
    # ── Legal HS football numbers: 0-99, one or two digits ──
    check("'12' legal", w._legal_football_jersey("12"))
    check("'0' legal", w._legal_football_jersey("0"))
    check("'99' legal", w._legal_football_jersey("99"))
    check("'#22' normalized + legal", w._legal_football_jersey("#22"))
    check("'100' illegal (3 digits)", not w._legal_football_jersey("100"))
    check("'7a' illegal", not w._legal_football_jersey("7a"))
    check("None illegal", not w._legal_football_jersey(None))
    check("'' illegal", not w._legal_football_jersey(""))

    # ── A confident primary read upgrades the play ──
    play = {}
    ok = w._apply_jersey_reads(play, {
        "primary_jersey": "24", "primary_confidence": 0.9,
        "players": [{"jersey": "24", "team": "offense", "role": "ball_carrier", "confidence": 0.9}],
    })
    check("confident read returns True", ok is True)
    check("sets primary_player_jersey", play.get("primary_player_jersey") == "24")
    check("mirrors ball_carrier_jersey", play.get("ball_carrier_jersey") == "24")
    check("tags source eagle_eye", play.get("jersey_source") == "eagle_eye")
    check("records confidence", play.get("jersey_confidence") == 0.9)
    check("keeps the players list", len(play.get("players", [])) == 1)

    # ── Below the confidence floor is NEVER accepted (never guess) ──
    p2 = {}
    check("low-confidence primary rejected",
          w._apply_jersey_reads(p2, {"primary_jersey": "7", "primary_confidence": 0.3, "players": []}) is False)
    check("no jersey written on low confidence", "primary_player_jersey" not in p2)

    # ── Illegal number rejected even at high confidence ──
    p3 = {}
    check("illegal primary rejected",
          w._apply_jersey_reads(p3, {"primary_jersey": "100", "primary_confidence": 0.95}) is False)

    # ── '#'-prefixed numbers normalized in primary AND players ──
    p4 = {}
    w._apply_jersey_reads(p4, {"primary_jersey": "#33", "primary_confidence": 0.8,
                               "players": [{"jersey": "#33", "confidence": 0.8}]})
    check("primary '#33' -> '33'", p4.get("primary_player_jersey") == "33")
    check("player '#33' -> '33'", p4.get("players", [{}])[0].get("jersey") == "33")

    # ── players list filters out sub-floor / illegal reads ──
    p5 = {}
    w._apply_jersey_reads(p5, {"primary_jersey": None, "primary_confidence": 0,
                               "players": [{"jersey": "10", "confidence": 0.9},
                                           {"jersey": "11", "confidence": 0.2},
                                           {"jersey": "999", "confidence": 0.9}]})
    kept = [pp["jersey"] for pp in p5.get("players", [])]
    check("keeps only legal + confident players", kept == ["10"])
    check("no primary set when primary_jersey null", "primary_player_jersey" not in p5)

    # ── Empty / null response is a no-op ──
    p6 = {"primary_player_jersey": "5"}
    check("empty resp is a no-op (returns False)", w._apply_jersey_reads(p6, {}) is False)
    check("empty resp leaves existing untouched", p6.get("primary_player_jersey") == "5")

    print(f"\n{'='*50}\n  {passed} passed, {failed} failed\n{'='*50}")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
