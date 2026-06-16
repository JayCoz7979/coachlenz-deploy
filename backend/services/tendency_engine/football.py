from typing import List, Dict, Any
from collections import Counter, defaultdict

# Play-type classification. Events are stored with event_type="play" and the
# specific call in play_type (e.g. "Run", "Pass", "Screen"). We classify run vs
# pass from play_type (case-insensitive), with a fallback to legacy event_type.
RUN_TYPES = {"run", "draw", "option", "qb sneak", "rush"}
PASS_TYPES = {"pass", "screen", "rpo", "play action", "play-action"}
SPECIAL_TYPES = {"punt", "kickoff", "field goal", "pat", "kick"}


def _is_play(e) -> bool:
    return e.event_type == "play" or e.event_type in ("run", "pass", "kick", "penalty") or bool(e.play_type)


def _kind(e) -> str:
    """Return 'run' | 'pass' | 'special' | 'other' for an event."""
    pt = (e.play_type or "").strip().lower()
    if pt in RUN_TYPES:
        return "run"
    if pt in PASS_TYPES:
        return "pass"
    if pt in SPECIAL_TYPES:
        return "special"
    if e.event_type == "run":
        return "run"
    if e.event_type == "pass":
        return "pass"
    if e.event_type == "kick":
        return "special"
    return "other"


def _is_run(e) -> bool:
    return _kind(e) == "run"


def _is_pass(e) -> bool:
    return _kind(e) == "pass"


def analyze_football(events) -> Dict[str, Any]:
    plays = [e for e in events if _is_play(e)]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    runs = [e for e in plays if _is_run(e)]
    passes = [e for e in plays if _is_pass(e)]

    rp_total = len(runs) + len(passes)
    run_pct = round(len(runs) / rp_total * 100, 1) if rp_total else 0
    pass_pct = round(len(passes) / rp_total * 100, 1) if rp_total else 0

    by_down = defaultdict(list)
    for e in plays:
        if e.down:
            by_down[e.down].append(e)

    down_tendencies = {}
    for down, down_plays in by_down.items():
        d_runs = [p for p in down_plays if _is_run(p)]
        d_passes = [p for p in down_plays if _is_pass(p)]
        d_rp = len(d_runs) + len(d_passes)
        down_tendencies[f"down_{down}"] = {
            "total": len(down_plays),
            "run_pct": round(len(d_runs) / d_rp * 100, 1) if d_rp else 0,
            "pass_pct": round(len(d_passes) / d_rp * 100, 1) if d_rp else 0,
        }

    formations = Counter(e.formation for e in plays if e.formation)
    top_formations = dict(formations.most_common(10))

    left_runs = [e for e in runs if e.hash_position == "left"]
    right_runs = [e for e in runs if e.hash_position == "right"]
    middle_runs = [e for e in runs if e.hash_position == "middle"]

    short_yardage = [e for e in plays if e.down in (3, 4) and e.distance and e.distance <= 3]
    sy_runs = [e for e in short_yardage if _is_run(e)]
    sy_run_pct = round(len(sy_runs) / len(short_yardage) * 100, 1) if short_yardage else 0

    red_zone = [e for e in plays if e.field_position and _is_red_zone(e.field_position)]
    rz_runs = [e for e in red_zone if _is_run(e)]
    rz_run_pct = round(len(rz_runs) / len(red_zone) * 100, 1) if red_zone else 0

    personnel = Counter(e.personnel for e in plays if e.personnel)

    motion_plays = [e for e in plays if e.motion]
    motion_pct = round(len(motion_plays) / total * 100, 1) if total else 0

    results = Counter(e.result for e in plays if e.result)
    yards = [e.yards_gained for e in plays if e.yards_gained is not None]
    avg_yards = round(sum(yards) / len(yards), 1) if yards else 0

    play_type_mix = Counter(e.play_type for e in plays if e.play_type)

    return {
        "total_plays": total,
        "run_plays": len(runs),
        "pass_plays": len(passes),
        "run_pass_ratio": {"run_pct": run_pct, "pass_pct": pass_pct},
        "play_type_mix": dict(play_type_mix.most_common(12)),
        "down_tendencies": down_tendencies,
        "top_formations": top_formations,
        "hash_tendencies": {
            "left_runs": len(left_runs),
            "right_runs": len(right_runs),
            "middle_runs": len(middle_runs),
        },
        "short_yardage": {"total": len(short_yardage), "run_pct": sy_run_pct},
        "red_zone": {"total": len(red_zone), "run_pct": rz_run_pct},
        "personnel_usage": dict(personnel.most_common(8)),
        "motion_pct": motion_pct,
        "play_results": dict(results.most_common(10)),
        "avg_yards_per_play": avg_yards,
        "first_down": _down_summary([e for e in plays if e.down == 1]),
        "second_long": _down_summary([e for e in plays if e.down == 2 and e.distance and e.distance >= 7]),
        "second_medium": _down_summary([e for e in plays if e.down == 2 and e.distance and 4 <= e.distance <= 6]),
        "second_short": _down_summary([e for e in plays if e.down == 2 and e.distance and e.distance <= 3]),
        "third_long": _down_summary([e for e in plays if e.down == 3 and e.distance and e.distance >= 7]),
        "third_medium": _down_summary([e for e in plays if e.down == 3 and e.distance and 4 <= e.distance <= 6]),
        "third_short": _down_summary([e for e in plays if e.down == 3 and e.distance and e.distance <= 3]),
        "fourth_down": _down_summary([e for e in plays if e.down == 4]),
    }


def _down_summary(plays) -> dict:
    if not plays:
        return {"total": 0}
    runs = [p for p in plays if _is_run(p)]
    passes = [p for p in plays if _is_pass(p)]
    rp = len(runs) + len(passes)
    return {
        "total": len(plays),
        "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
        "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
        "top_plays": dict(Counter(p.play_type for p in plays if p.play_type).most_common(5)),
    }


def analyze_football_defense(events) -> Dict[str, Any]:
    """Defensive tendencies for the scouted team's defense (front, coverage, blitz)."""
    plays = [e for e in events if _is_play(e)]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    fronts = Counter(e.defensive_front for e in plays if e.defensive_front)
    coverages = Counter(e.coverage for e in plays if e.coverage)
    blitzes = [e for e in plays if e.blitz and e.blitz.lower() not in ("", "none", "no")]
    blitz_pct = round(len(blitzes) / total * 100, 1) if total else 0
    blitz_types = Counter(e.blitz for e in blitzes if e.blitz)

    # Coverage by down
    by_down = defaultdict(list)
    for e in plays:
        if e.down:
            by_down[e.down].append(e)
    coverage_by_down = {}
    for down, dp in by_down.items():
        cov = Counter(p.coverage for p in dp if p.coverage)
        coverage_by_down[f"down_{down}"] = {"total": len(dp), "coverages": dict(cov.most_common(4))}

    # Blitz on passing downs (3rd & 6+)
    passing_downs = [e for e in plays if e.down == 3 and e.distance and e.distance >= 6]
    pd_blitz = [e for e in passing_downs if e in blitzes]
    pd_blitz_pct = round(len(pd_blitz) / len(passing_downs) * 100, 1) if passing_downs else 0

    results = Counter(e.result for e in plays if e.result)

    return {
        "total_plays": total,
        "top_fronts": dict(fronts.most_common(8)),
        "top_coverages": dict(coverages.most_common(8)),
        "blitz_pct": blitz_pct,
        "blitz_types": dict(blitz_types.most_common(8)),
        "coverage_by_down": coverage_by_down,
        "third_long_blitz_pct": pd_blitz_pct,
        "play_results": dict(results.most_common(10)),
    }


def _is_red_zone(field_position: str) -> bool:
    try:
        parts = field_position.split()
        if len(parts) >= 2 and parts[0].upper() == "OPP":
            return int(parts[1]) <= 20
    except Exception:
        pass
    return False
