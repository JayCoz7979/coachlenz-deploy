"""Player-level tendency tracking (charter Component 1 — "every player").

Single-camera, jersey-based. We only track players whose jersey number the AI
could legibly read; players without a legible number are not invented. Every
player block carries a coverage/confidence note so coaches know the limits.
"""
from typing import List, Dict, Any
from collections import Counter, defaultdict
from .football import _x, _is_success, _is_explosive, _is_run, _is_pass


def _players_of(e) -> list:
    ps = _x(e, "players")
    return ps if isinstance(ps, list) else []


def _primary_jersey(e):
    j = _x(e, "primary_player_jersey")
    return str(j) if j not in (None, "") else None


def _made(e) -> bool:
    return (e.result or "").lower() in ("made", "good", "and-1")


def _is_three(e) -> bool:
    z = _x(e, "shot_zone") or ""
    return "3" in z or "Corner" in z or "Wing 3" in z or "Top of Key" in z


def _primary_team(e) -> str:
    """Team of the primary actor: prefer the matching players entry, else event side."""
    pj = _primary_jersey(e)
    for p in _players_of(e):
        if str(p.get("jersey")) == pj and p.get("team"):
            return p["team"]
    return "defense" if (e.side or "offense") == "defense" else "offense"


def analyze_players(events, sport: str) -> Dict[str, Any]:
    sport = (sport or "football").lower()
    total = len(events)
    if total == 0:
        return {"tracked": False, "players_identified": 0}

    with_players = [e for e in events if _players_of(e) or _primary_jersey(e)]
    if not with_players:
        return {
            "tracked": False,
            "players_identified": 0,
            "coverage": {"events_with_players": 0, "total_events": total, "pct": 0.0},
            "note": "No legible jersey numbers were read on this film (single-camera limit). "
                    "Player-level tendencies need readable jerseys — closer or higher-angle film improves this.",
        }

    # appearances + role counts across every legible sighting
    agg: Dict[str, dict] = defaultdict(lambda: {
        "jersey": None, "team": None, "appearances": 0, "roles": Counter(),
        "confidences": [], "primary_events": [],
    })

    for e in events:
        for p in _players_of(e):
            jersey = p.get("jersey")
            team = p.get("team")
            if jersey is None or team is None:
                continue
            key = f"{team}#{jersey}"
            a = agg[key]
            a["jersey"], a["team"] = str(jersey), team
            a["appearances"] += 1
            if p.get("role"):
                a["roles"][p["role"]] += 1
            c = p.get("confidence")
            if isinstance(c, (int, float)):
                a["confidences"].append(float(c))

        pj = _primary_jersey(e)
        if pj:
            key = f"{_primary_team(e)}#{pj}"
            a = agg[key]
            a["jersey"], a["team"] = pj, _primary_team(e)
            a["primary_events"].append(e)

    builder = _football_player if sport in ("football", "flag_football") else \
        (_basketball_player if sport == "basketball" else _generic_player)

    by_player = {}
    for key, a in agg.items():
        confs = a["confidences"]
        block = {
            "jersey": a["jersey"],
            "team": a["team"],
            "appearances": a["appearances"],
            "as_primary": len(a["primary_events"]),
            "roles": dict(a["roles"].most_common()),
            "avg_id_confidence": round(sum(confs) / len(confs), 2) if confs else None,
        }
        block.update(builder(a["primary_events"], a["roles"]))
        by_player[key] = block

    # rank by involvement (primary touches, then appearances)
    ranked = sorted(by_player.items(), key=lambda kv: (kv[1]["as_primary"], kv[1]["appearances"]), reverse=True)
    by_player = {k: v for k, v in ranked}

    return {
        "tracked": True,
        "players_identified": len(by_player),
        "coverage": {
            "events_with_players": len(with_players),
            "total_events": total,
            "pct": round(len(with_players) / total * 100, 1),
        },
        "by_player": by_player,
        "most_involved": ranked[0][0] if ranked else None,
        "note": "Single-camera, jersey-based. Only players with a legible jersey number are tracked; "
                "unreadable numbers are omitted rather than guessed.",
    }


def _football_player(primary_events, roles) -> Dict[str, Any]:
    if not primary_events:
        return {}
    yards = [e.yards_gained for e in primary_events if e.yards_gained is not None]
    succ = [e for e in primary_events if _is_success(e)]
    expl = [e for e in primary_events if _is_explosive(e)]
    carries = [e for e in primary_events if _is_run(e)]
    pass_plays = [e for e in primary_events if _is_pass(e)]
    return {
        "touches": len(primary_events),
        "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
        "total_yards": sum(yards) if yards else 0,
        "success_rate": round(len(succ) / len(primary_events) * 100, 1) if primary_events else 0,
        "explosive_plays": len(expl),
        "as_runner": len(carries),
        "as_passer_or_receiver": len(pass_plays),
        "by_play_type": dict(Counter(e.play_type for e in primary_events if e.play_type).most_common(6)),
        "by_down": dict(Counter(e.down for e in primary_events if e.down)),
    }


def _basketball_player(primary_events, roles) -> Dict[str, Any]:
    shots = [e for e in primary_events if e.event_type == "shot"]
    makes = [e for e in shots if _made(e)]
    threes = [e for e in shots if _is_three(e)]
    threes_made = [e for e in threes if _made(e)]
    tos = [e for e in primary_events if e.event_type == "turnover"]
    return {
        "shot_attempts": len(shots),
        "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
        "three_attempts": len(threes),
        "three_pct": round(len(threes_made) / len(threes) * 100, 1) if threes else 0,
        "turnovers": len(tos),
        "by_zone": dict(Counter(_x(e, "shot_zone") for e in shots if _x(e, "shot_zone")).most_common(6)),
        "by_action": dict(Counter(_x(e, "play_action") for e in primary_events if _x(e, "play_action")).most_common(6)),
        # role-based involvement even when not the primary scorer
        "assists": roles.get("assister", 0),
        "rebounds": roles.get("rebounder", 0),
        "steals": roles.get("stealer", 0),
        "blocks": roles.get("blocker", 0),
    }


def _generic_player(primary_events, roles) -> Dict[str, Any]:
    return {"events_as_primary": len(primary_events)}
