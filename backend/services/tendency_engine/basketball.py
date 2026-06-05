from typing import List, Dict, Any
from collections import Counter, defaultdict

def analyze_basketball(events) -> Dict[str, Any]:
    plays = [e for e in events if e.event_type in ("shot","turnover","foul","rebound","assist","steal","block","timeout")]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    shots = [e for e in plays if e.event_type == "shot"]
    makes = [e for e in shots if e.result == "made"]
    misses = [e for e in shots if e.result == "missed"]
    fg_pct = round(len(makes) / len(shots) * 100, 1) if shots else 0

    shot_zones = Counter(e.field_position for e in shots if e.field_position)
    play_types = Counter(e.play_type for e in shots if e.play_type)
    turnovers = [e for e in plays if e.event_type == "turnover"]
    to_types = Counter(e.play_type for e in turnovers if e.play_type)

    offensive = [e for e in plays if e.extra_data and e.extra_data.get("side") == "offense"]
    defensive = [e for e in plays if e.extra_data and e.extra_data.get("side") == "defense"]

    half_court = [e for e in shots if not (e.extra_data or {}).get("transition")]
    transition = [e for e in shots if (e.extra_data or {}).get("transition")]

    return {
        "total_plays": total,
        "shooting": {
            "total_shots": len(shots),
            "makes": len(makes),
            "misses": len(misses),
            "fg_pct": fg_pct,
        },
        "shot_zones": dict(shot_zones.most_common(10)),
        "shot_types": dict(play_types.most_common(10)),
        "turnovers": {
            "total": len(turnovers),
            "types": dict(to_types.most_common(8)),
        },
        "half_court_shots": len(half_court),
        "transition_shots": len(transition),
        "timeouts": len([e for e in plays if e.event_type == "timeout"]),
        "fouls": len([e for e in plays if e.event_type == "foul"]),
    }
