from fastapi import APIRouter, HTTPException, Depends
from lib.supabase_client import get_table
from lib.auth import get_current_coach
from datetime import datetime, timezone

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/team/{team_id}")
async def get_team_dashboard(team_id: str, coach: dict = Depends(get_current_coach)):
    """Team season summary: record, top performers, next game, recent practice."""
    team_result = get_table("teams").select("*").eq("id", team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    team = team_result.data[0]
    now_iso = datetime.now(timezone.utc).isoformat()

    # Season record (W-L-T)
    games_result = get_table("games").select("result").eq("team_id", team_id).execute()
    record = {"wins": 0, "losses": 0, "ties": 0, "unplayed": 0}
    for g in games_result.data:
        r = g.get("result")
        if r == "win":
            record["wins"] += 1
        elif r == "loss":
            record["losses"] += 1
        elif r == "tie":
            record["ties"] += 1
        else:
            record["unplayed"] += 1

    # Next upcoming game
    upcoming_result = (
        get_table("games")
        .select("*")
        .eq("team_id", team_id)
        .gte("date", now_iso)
        .order("date")
        .limit(3)
        .execute()
    )

    # Last 3 practice plans
    recent_practice_result = (
        get_table("practice_plans")
        .select("id, date, title, duration_minutes")
        .eq("team_id", team_id)
        .order("date", desc=True)
        .limit(3)
        .execute()
    )

    # Player health: count active/injured/inactive
    players_result = (
        get_table("players")
        .select("id, name, jersey_number, position, status")
        .eq("team_id", team_id)
        .execute()
    )
    players = players_result.data
    health = {"active": 0, "injured": 0, "inactive": 0, "total": len(players)}
    for p in players:
        s = p.get("status", "active")
        health[s] = health.get(s, 0) + 1

    player_ids = [p["id"] for p in players]

    # Top performers: players with most stats recorded
    top_performers = []
    if player_ids:
        stats_result = (
            get_table("player_stats")
            .select("player_id, stats")
            .in_("player_id", player_ids)
            .execute()
        )

        # Aggregate primary stats per player
        player_stats_agg: dict = {}
        for stat in stats_result.data:
            pid = stat["player_id"]
            if pid not in player_stats_agg:
                player_stats_agg[pid] = {"count": 0, "stats_sum": {}}
            player_stats_agg[pid]["count"] += 1
            for key, val in stat.get("stats", {}).items():
                if isinstance(val, (int, float)):
                    player_stats_agg[pid]["stats_sum"][key] = (
                        player_stats_agg[pid]["stats_sum"].get(key, 0) + val
                    )

        player_map = {p["id"]: p for p in players}
        sorted_players = sorted(
            player_stats_agg.items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:3]

        top_performers = [
            {
                "player": player_map.get(pid, {}),
                "games_with_stats": data["count"],
                "season_totals": data["stats_sum"],
            }
            for pid, data in sorted_players
        ]

    return {
        "team": team,
        "season_record": record,
        "upcoming_games": upcoming_result.data,
        "recent_practices": recent_practice_result.data,
        "team_health": health,
        "top_performers": top_performers,
        "roster_size": len(players),
    }
