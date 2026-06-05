from typing import List, Dict, Any
from collections import Counter, defaultdict
from .football import _down_summary

def analyze_flag_football(events) -> Dict[str, Any]:
    plays = [e for e in events if e.event_type in ("run", "pass", "penalty")]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    runs = [e for e in plays if e.event_type == "run"]
    passes = [e for e in plays if e.event_type == "pass"]

    formations = Counter(e.formation for e in plays if e.formation)
    routes = Counter(e.play_type for e in plays if e.play_type and e.event_type == "pass")
    results = Counter(e.result for e in plays if e.result)
    yards = [e.yards_gained for e in plays if e.yards_gained is not None]

    by_down = defaultdict(list)
    for e in plays:
        if e.down:
            by_down[e.down].append(e)

    return {
        "total_plays": total,
        "run_pass_ratio": {
            "run_pct": round(len(runs) / total * 100, 1),
            "pass_pct": round(len(passes) / total * 100, 1),
        },
        "top_formations": dict(formations.most_common(8)),
        "top_routes": dict(routes.most_common(8)),
        "play_results": dict(results.most_common(10)),
        "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
        "down_tendencies": {
            f"down_{d}": _down_summary(ps) for d, ps in by_down.items()
        },
        "first_down": _down_summary([e for e in plays if e.down == 1]),
        "second_down": _down_summary([e for e in plays if e.down == 2]),
        "third_down": _down_summary([e for e in plays if e.down == 3]),
    }
