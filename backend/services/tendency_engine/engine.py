from typing import List, Dict, Any
from backend.models.event import Event


def _side(e) -> str:
    return (getattr(e, "side", None) or "offense").lower()


async def run_tendency_engine(sport: str, events: List[Event]) -> Dict[str, Any]:
    from .football import analyze_football, analyze_football_defense
    from .basketball import analyze_basketball
    from .flag_football import analyze_flag_football
    from .base_sports import analyze_base_sport

    if sport in ("football", "flag_football"):
        offense = [e for e in events if _side(e) != "defense"]
        defense = [e for e in events if _side(e) == "defense"]
        off = analyze_flag_football(offense) if sport == "flag_football" else analyze_football(offense)
        deff = analyze_football_defense(defense)
        return {
            "total_plays": off.get("total_plays", 0) + deff.get("total_plays", 0),
            "offense_plays": off.get("total_plays", 0),
            "defense_plays": deff.get("total_plays", 0),
            "offense": off,
            "defense": deff,
        }
    elif sport == "basketball":
        return analyze_basketball(events)
    else:
        return analyze_base_sport(sport, events)
