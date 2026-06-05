from typing import List, Dict, Any
from backend.models.event import Event

async def run_tendency_engine(sport: str, events: List[Event]) -> Dict[str, Any]:
    from .football import analyze_football
    from .basketball import analyze_basketball
    from .flag_football import analyze_flag_football
    from .base_sports import analyze_base_sport

    if sport == "football":
        return analyze_football(events)
    elif sport == "basketball":
        return analyze_basketball(events)
    elif sport == "flag_football":
        return analyze_flag_football(events)
    else:
        return analyze_base_sport(sport, events)
