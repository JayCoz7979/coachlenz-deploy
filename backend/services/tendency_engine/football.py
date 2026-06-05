from typing import List, Dict, Any
from collections import Counter, defaultdict

def analyze_football(events) -> Dict[str, Any]:
    plays = [e for e in events if e.event_type in ("run", "pass", "kick", "penalty")]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    runs = [e for e in plays if e.event_type == "run"]
    passes = [e for e in plays if e.event_type == "pass"]

    run_pct = round(len(runs) / total * 100, 1) if total else 0
    pass_pct = round(len(passes) / total * 100, 1) if total else 0

    # Down and distance tendencies
    by_down = defaultdict(list)
    for e in plays:
        if e.down:
            by_down[e.down].append(e)

    down_tendencies = {}
    for down, down_plays in by_down.items():
        d_runs = [p for p in down_plays if p.event_type == "run"]
        d_passes = [p for p in down_plays if p.event_type == "pass"]
        down_tendencies[f"down_{down}"] = {
            "total": len(down_plays),
            "run_pct": round(len(d_runs) / len(down_plays) * 100, 1),
            "pass_pct": round(len(d_passes) / len(down_plays) * 100, 1),
        }

    # Formation tendencies
    formations = Counter(e.formation for e in plays if e.formation)
    top_formations = dict(formations.most_common(10))

    # Hash tendencies
    left_runs = [e for e in runs if e.hash_position == "left"]
    right_runs = [e for e in runs if e.hash_position == "right"]
    middle_runs = [e for e in runs if e.hash_position == "middle"]

    # Short yardage (3rd/4th and 1-3)
    short_yardage = [e for e in plays if e.down in (3, 4) and e.distance and e.distance <= 3]
    sy_runs = [e for e in short_yardage if e.event_type == "run"]
    sy_run_pct = round(len(sy_runs) / len(short_yardage) * 100, 1) if short_yardage else 0

    # Red zone (inside 20)
    red_zone = [e for e in plays if e.field_position and _is_red_zone(e.field_position)]
    rz_runs = [e for e in red_zone if e.event_type == "run"]
    rz_run_pct = round(len(rz_runs) / len(red_zone) * 100, 1) if red_zone else 0

    # Personnel groupings
    personnel = Counter(e.personnel for e in plays if e.personnel)

    # Motion usage
    motion_plays = [e for e in plays if e.motion]
    motion_pct = round(len(motion_plays) / total * 100, 1) if total else 0

    # Play results
    results = Counter(e.result for e in plays if e.result)
    yards = [e.yards_gained for e in plays if e.yards_gained is not None]
    avg_yards = round(sum(yards) / len(yards), 1) if yards else 0

    return {
        "total_plays": total,
        "run_pass_ratio": {"run_pct": run_pct, "pass_pct": pass_pct},
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
        # 1st down
        "first_down": _down_summary([e for e in plays if e.down == 1]),
        # 2nd and long (7+)
        "second_long": _down_summary([e for e in plays if e.down == 2 and e.distance and e.distance >= 7]),
        # 2nd and medium (4-6)
        "second_medium": _down_summary([e for e in plays if e.down == 2 and e.distance and 4 <= e.distance <= 6]),
        # 2nd and short (1-3)
        "second_short": _down_summary([e for e in plays if e.down == 2 and e.distance and e.distance <= 3]),
        # 3rd and long
        "third_long": _down_summary([e for e in plays if e.down == 3 and e.distance and e.distance >= 7]),
        # 3rd and medium
        "third_medium": _down_summary([e for e in plays if e.down == 3 and e.distance and 4 <= e.distance <= 6]),
        # 3rd and short
        "third_short": _down_summary([e for e in plays if e.down == 3 and e.distance and e.distance <= 3]),
        # 4th down
        "fourth_down": _down_summary([e for e in plays if e.down == 4]),
    }

def _down_summary(plays) -> dict:
    if not plays:
        return {"total": 0}
    runs = [p for p in plays if p.event_type == "run"]
    passes = [p for p in plays if p.event_type == "pass"]
    return {
        "total": len(plays),
        "run_pct": round(len(runs) / len(plays) * 100, 1),
        "pass_pct": round(len(passes) / len(plays) * 100, 1),
        "top_plays": dict(Counter(p.play_type for p in plays if p.play_type).most_common(5)),
    }

def _is_red_zone(field_position: str) -> bool:
    try:
        parts = field_position.split()
        if len(parts) >= 2 and parts[0].upper() == "OPP":
            return int(parts[1]) <= 20
    except Exception:
        pass
    return False
