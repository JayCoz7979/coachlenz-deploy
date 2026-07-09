"""
Synthetic-data test for the Auto Scouting Keys layer (scouting_keys) — the
plain-English tendency generator and its self-scout twin.

Builds an offense with deliberately loud tendencies:
  • Trips Rt + motion on 3rd & medium: pass 7 of 8, favoring Y-Cross
        -> a featured PRE-SNAP TELL key (and a self-scout giveaway)
  • Inside Zone from I-Form on 1st & 10, several explosive
        -> a run-game key + an explosive-threat key + a winning concept (self-scout)
  • penalties + negative plays
        -> self-inflicted items (self-scout)
  • a defense that blitzes 3rd & long                          -> a pressure key

Asserts the keys generate, rank most-exploitable first, carry sample + confidence,
surface the pre-snap tell, and that build_football_scouting_report exposes both
scouting_keys and a populated self_scout view.

Run:  python -m backend.tests.test_scouting_keys
"""
from types import SimpleNamespace

from backend.services.tendency_engine.football import (
    analyze_football, analyze_football_defense, analyze_football_special,
)
from backend.services.tendency_engine.football_scout import build_football_scouting_report
from backend.services.tendency_engine.scouting_keys import (
    build_scouting_keys, build_self_scout,
)


def P(side="offense", **cols):
    """A play event. Direct columns become attributes; the rest go to extra_data."""
    direct = {}
    for k in ("down", "distance", "field_position", "hash_position", "formation",
              "personnel", "play_type", "motion", "result", "yards_gained",
              "time_seconds", "defensive_front", "coverage", "blitz"):
        direct[k] = cols.pop(k, None)
    direct["motion"] = bool(direct.get("motion"))
    return SimpleNamespace(event_type="play", side=side, extra_data=cols, **direct)


def META(**kw):
    return SimpleNamespace(event_type="scout_meta", side="meta", extra_data=kw,
                           down=None, distance=None, play_type=None)


def build_events():
    ev = [META(analyst_id="coach_a", analyst="coach_a", reviewer_id="coach_b",
               reviewer="coach_b", status="reviewed", games_scouted=3)]

    # ── Loud pre-snap tell: Trips Rt + motion, 3rd & 5 (medium), pass 7 of 8. ──
    for i in range(7):
        ev.append(P(side="offense", down=3, distance=5, field_position="OWN 45",
                    formation="Trips Rt", personnel="11", motion=True,
                    play_type="pass", pass_concept="Y-Cross",
                    yards_gained=[8, 12, 6, 3, 14, 9, 7][i],
                    result="first down" if [8, 12, 6, 3, 14, 9, 7][i] >= 5 else "incomplete"))
    ev.append(P(side="offense", down=3, distance=5, field_position="OWN 45",
                formation="Trips Rt", personnel="11", motion=True,
                play_type="run", run_concept="Draw", yards_gained=2, result="gain"))

    # ── Inside Zone from I-Form on 1st & 10: bread-and-butter + explosive. ──
    iz = [5, 4, 12, 6, 4, 15, 5, 4, 11, 6, 4, 3]   # 3 explosive (>=10), mostly successful
    for i, y in enumerate(iz):
        ev.append(P(side="offense", down=1, distance=10, field_position="OWN 30",
                    formation="I-Form", personnel="21", motion=False,
                    play_type="run", run_concept="Inside Zone", run_direction="Inside Left",
                    yards_gained=y, result="first down" if y >= 10 else "gain"))

    # ── Self-inflicted wounds: penalties + negative plays. ──
    for _ in range(3):
        ev.append(P(side="offense", down=2, distance=8, formation="Shotgun",
                    play_type="pass", yards_gained=0, result="Penalty"))
    for _ in range(2):
        ev.append(P(side="offense", down=2, distance=10, formation="Shotgun",
                    play_type="run", run_concept="Power O", yards_gained=-2, result="loss"))

    # ── Defense: blitz-heavy on 3rd & long behind Cover 3. ──
    for i in range(9):
        ev.append(P(side="defense", down=3, distance=8, formation="Empty",
                    defensive_front="Even", coverage="Cover 3",
                    blitz="Edge" if i < 6 else "None", yards_gained=5, result="gain"))

    return ev


def run():
    events = build_events()
    offense = [e for e in events if getattr(e, "side", None) == "offense"]
    defense = [e for e in events if getattr(e, "side", None) == "defense"]
    special = [e for e in events if getattr(e, "side", None) == "special_teams"]

    off = analyze_football(offense)
    deff = analyze_football_defense(defense)
    st = analyze_football_special(special)

    passed, failed = 0, 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")

    # ── OPPONENT KEYS ────────────────────────────────────────────────────────
    keys = build_scouting_keys(off, deff, st)
    print(f"\nGenerated {len(keys)} scouting keys:")
    for k in keys[:8]:
        print(f"   [{k['confidence']}|str={k['strength']}|n={k['sample']}] {k['statement']}")

    check("keys generated", len(keys) >= 4)
    check("every key carries sample + confidence + strength + exploit",
          all(k.get("sample") and k.get("confidence") and "strength" in k and k.get("exploit") for k in keys))
    check("no non-featured key below the 5-rep floor",
          all(k["sample"] >= 5 for k in keys if not k["featured"]))

    # Ranking: featured first, then non-increasing strength within the non-featured tail.
    feat = [k for k in keys if k["featured"]]
    nonfeat = [k for k in keys if not k["featured"]]
    check("featured keys rank ahead of non-featured",
          all(keys.index(f) < keys.index(n) for f in feat for n in nonfeat) if feat and nonfeat else True)
    check("non-featured keys sorted by strength desc",
          all(nonfeat[i]["strength"] >= nonfeat[i + 1]["strength"] for i in range(len(nonfeat) - 1)))

    tells = [k for k in keys if k["category"] == "Pre-Snap Tell"]
    check("pre-snap tell surfaced", len(tells) >= 1)
    trips = next((k for k in tells if "Trips Rt" in k["statement"]), None)
    check("pre-snap tell names the formation + concept",
          bool(trips) and "Y-Cross" in trips["statement"])
    check("dominant tell is featured (>=75% lean)", bool(trips) and trips["featured"])

    check("run bread-and-butter key present",
          any(k["category"] == "Run Game" and "Inside Zone" in k["statement"] for k in keys))
    check("explosive-threat key present and featured",
          any(k["category"] == "Explosive Threat" and k["featured"] for k in keys))
    check("defensive pressure key present",
          any(k["category"].startswith("Defense") for k in keys))
    check("priority numbering applied", all("priority" in k for k in keys))

    # ── SELF-SCOUT ───────────────────────────────────────────────────────────
    ss = build_self_scout(off, deff, st)
    print(f"\nSelf-scout: {ss.get('summary')}")
    for p in ss.get("predictability", [])[:5]:
        print(f"   TIP  {p['statement']}  | Fix: {p['fix']}")
    for w in ss.get("winning_concepts", [])[:5]:
        print(f"   WIN  {w['statement']}")
    for s in ss.get("self_inflicted", []):
        print(f"   HURT {s['statement']}")

    check("self-scout available", ss.get("available") is True)
    check("predictability flags found", len(ss.get("predictability", [])) >= 1)
    check("biggest giveaway named", bool(ss.get("biggest_giveaway")))
    check("predictability carries a fix", all(p.get("fix") for p in ss.get("predictability", [])))
    check("winning concept surfaced (Inside Zone)",
          any("Inside Zone" in w["statement"] for w in ss.get("winning_concepts", [])))
    check("self-inflicted: penalties flagged",
          any("penalt" in s["statement"].lower() for s in ss.get("self_inflicted", [])))
    check("self-inflicted: negative plays flagged",
          any("negative" in s["statement"].lower() for s in ss.get("self_inflicted", [])))

    # ── WIRED INTO THE SCOUTING BLOCK ────────────────────────────────────────
    report = build_football_scouting_report(events, off, deff, st)
    check("scouting block exposes scouting_keys", bool(report.get("scouting_keys")))
    check("scouting block exposes populated self_scout",
          (report.get("self_scout") or {}).get("available") is True)

    print(f"\n{'='*52}\n  {passed} passed, {failed} failed\n{'='*52}")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
