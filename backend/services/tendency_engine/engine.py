from typing import List, Dict, Any
from collections import Counter
from backend.models.event import Event


def _side(e) -> str:
    return (getattr(e, "side", None) or "offense").lower()


def _coverage_report(events: List[Event]) -> Dict[str, Any]:
    """Single-camera transparency: confidence distribution and named blind spots.

    Implements the UATP requirement and the charter's single-camera honesty rule —
    surface what the fixed angle could not confidently read, never hide it.
    """
    total = len(events)
    if total == 0:
        return {"total_events": 0}

    confidences = []
    blind_spots = []
    for e in events:
        ed = getattr(e, "extra_data", None) or {}
        c = ed.get("confidence")
        if isinstance(c, (int, float)):
            confidences.append(float(c))
        bs = ed.get("blind_spot")
        if bs:
            blind_spots.append(str(bs))

    high = [c for c in confidences if c >= 0.8]
    medium = [c for c in confidences if 0.6 <= c < 0.8]
    low = [c for c in confidences if c < 0.6]
    avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else None

    # Overall confidence band — drives how strongly reports should be worded
    if avg_conf is None:
        band = "unknown"
    elif avg_conf >= 0.8:
        band = "high"
    elif avg_conf >= 0.65:
        band = "medium"
    else:
        band = "low"

    top_blind_spots = Counter(blind_spots).most_common(8)

    return {
        "total_events": total,
        "events_scored": len(confidences),
        "avg_confidence": avg_conf,
        "confidence_band": band,
        "high_confidence_count": len(high),
        "medium_confidence_count": len(medium),
        "low_confidence_count": len(low),
        "low_confidence_pct": round(len(low) / len(confidences) * 100, 1) if confidences else 0,
        "blind_spot_count": len(blind_spots),
        "blind_spot_pct": round(len(blind_spots) / total * 100, 1) if total else 0,
        "top_blind_spots": [{"limitation": k, "count": v} for k, v in top_blind_spots],
    }


async def run_tendency_engine(sport: str, events: List[Event]) -> Dict[str, Any]:
    from .football import analyze_football, analyze_football_defense, analyze_football_special
    from .basketball import analyze_basketball
    from .flag_football import analyze_flag_football
    from .base_sports import analyze_base_sport
    from .players import analyze_players

    if sport in ("football", "flag_football"):
        offense = [e for e in events if _side(e) == "offense"]
        defense = [e for e in events if _side(e) == "defense"]
        special = [e for e in events if _side(e) == "special_teams"]
        off = analyze_flag_football(offense) if sport == "flag_football" else analyze_football(offense)
        deff = analyze_football_defense(defense)
        st = analyze_football_special(special)
        result = {
            "total_plays": off.get("total_plays", 0) + deff.get("total_plays", 0) + st.get("total_plays", 0),
            "offense_plays": off.get("total_plays", 0),
            "defense_plays": deff.get("total_plays", 0),
            "special_teams_plays": st.get("total_plays", 0),
            "offense": off,
            "defense": deff,
            "special_teams": st,
            "data_confidence": _coverage_report(events),
            "player_tendencies": analyze_players(events, sport),
        }
        # Coordinator layer: validation gates (Module 7), situational tendency
        # statements (Module 3 summary), and the installable game plan (Module 8).
        # Same pattern as basketball's `scouting` block — 11-man football only.
        if sport == "football":
            from .football_scout import build_football_scouting_report
            result["scouting"] = build_football_scouting_report(events, off, deff, st)
        return result

    elif sport == "basketball":
        result = analyze_basketball(events)
        # Coordinator layer: eight validation gates (Module 10), situational
        # tendency statements (Gate 6 translation), the installable game plan
        # (Module 11), advanced metrics + late-game + free-throw + special
        # situations + player profiles + single-camera confidence (Modules 5/7/8/9/12).
        # It wraps the six-category scout, returning a superset so every consumer
        # that reads the category_* keys keeps working untouched.
        from .basketball_scout_validation import build_basketball_scouting_report
        six_cat = result.get("scouting", {}) or {}
        if six_cat.get("available"):
            result["scouting"] = build_basketball_scouting_report(events, result, six_cat)
        result["data_confidence"] = _coverage_report(events)
        result["player_tendencies"] = analyze_players(events, sport)
        return result

    else:
        result = analyze_base_sport(sport, events)
        if isinstance(result, dict):
            result["data_confidence"] = _coverage_report(events)
            result["player_tendencies"] = analyze_players(events, sport)
        return result
