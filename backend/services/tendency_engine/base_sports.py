from typing import List, Dict, Any
from collections import Counter

def analyze_base_sport(sport: str, events) -> Dict[str, Any]:
    total = len(events)
    if total == 0:
        return {"total_plays": 0, "sport": sport}

    event_types = Counter(e.event_type for e in events)
    results = Counter(e.result for e in events if e.result)
    play_types = Counter(e.play_type for e in events if e.play_type)
    yards = [e.yards_gained for e in events if e.yards_gained is not None]

    return {
        "sport": sport,
        "total_events": total,
        "event_types": dict(event_types.most_common(15)),
        "results": dict(results.most_common(10)),
        "play_types": dict(play_types.most_common(10)),
        "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
    }
