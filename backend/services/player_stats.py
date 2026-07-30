"""
Per-player season stats — pure and unit-testable (no DB, no framework).

Stats are derived on demand from a team's play Events rather than materialized: the
team already scopes a season (Team.season), so aggregating that team's game Events is
always fresh and needs no "update after each analysis" hook or extra table.

Each Event carries a primary-actor jersey (Event.player) and a per-play cast in
extra_data["players"] (a list of {jersey, role, ...}). We normalize jerseys the same
way the roster does (07 == 7) so reads tie back to named players.
"""
from typing import Any, Dict, Iterable, List

from backend.services.roster import normalize_jersey


def _blank() -> Dict[str, Any]:
    return {
        "plays": 0,            # distinct plays the jersey appears in (primary or cast)
        "primary_plays": 0,    # plays where the jersey is the primary actor
        "total_yards": 0,      # yards on primary plays (ball-carrier / passer)
        "_games": set(),       # distinct game ids (collapsed to a count on finalize)
        "by_play_type": {},    # primary plays split by play_type
        "by_role": {},         # cast appearances split by role
    }


def _bump(counter: Dict[str, int], key: Any) -> None:
    k = (str(key).strip() if key is not None else "")
    if not k:
        return
    counter[k] = counter.get(k, 0) + 1


def aggregate_player_stats(events: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """Aggregate a season's Events into per-jersey stat lines.

    `events` is any iterable of Event-like objects (real ORM rows or SimpleNamespace).
    Returns {normalized_jersey: stat_line}. scout_meta rows are ignored. A jersey that
    is both the primary actor and listed in the cast on the same play counts that play
    once toward `plays` and once toward `primary_plays`.
    """
    stats: Dict[str, Dict[str, Any]] = {}

    def line(jersey: str) -> Dict[str, Any]:
        return stats.setdefault(jersey, _blank())

    for e in events:
        if getattr(e, "event_type", None) == "scout_meta":
            continue

        game_id = str(getattr(e, "game_id", "") or "")
        play_type = getattr(e, "play_type", None)
        yards = getattr(e, "yards_gained", None)
        extra = getattr(e, "extra_data", None) or {}

        involved: set = set()

        primary = normalize_jersey(getattr(e, "player", None))
        if primary:
            involved.add(primary)
            s = line(primary)
            s["primary_plays"] += 1
            _bump(s["by_play_type"], play_type)
            if isinstance(yards, (int, float)) and not isinstance(yards, bool):
                s["total_yards"] += int(yards)

        for cast in (extra.get("players") or []):
            if not isinstance(cast, dict):
                continue
            j = normalize_jersey(cast.get("jersey"))
            if not j:
                continue
            involved.add(j)
            _bump(line(j)["by_role"], cast.get("role"))

        for j in involved:
            s = line(j)
            s["plays"] += 1
            s["_games"].add(game_id)

    # Collapse the private game-id set into a count.
    return {j: {**{k: v for k, v in s.items() if k != "_games"}, "games": len(s["_games"])}
            for j, s in stats.items()}


def stat_line_for(events: Iterable[Any], jersey: Any) -> Dict[str, Any]:
    """The single stat line for one jersey (zeros if the jersey never appears)."""
    key = normalize_jersey(jersey)
    agg = aggregate_player_stats(events)
    if key in agg:
        return agg[key]
    blank = _blank()
    return {**{k: v for k, v in blank.items() if k != "_games"}, "games": 0}


def top_play_types(stat_line: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
    """The most common play types for a stat line, highest first — a compact headline
    for a profile card (e.g. 'Run 24, Pass 11')."""
    items = sorted((stat_line.get("by_play_type") or {}).items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"play_type": k, "count": v} for k, v in items[:limit]]
