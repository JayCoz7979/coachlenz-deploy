import os
import json
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, Any
import anthropic
from lib.supabase_client import get_table
from lib.auth import get_current_coach
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/stats", tags=["stats"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class StatRecord(BaseModel):
    player_id: str
    game_id: Optional[str] = None
    sport: str
    stats: dict[str, Any]


class AIAnalysisRequest(BaseModel):
    player_id: str
    additional_context: Optional[str] = None


VALID_SPORTS = {"football", "basketball", "baseball", "softball", "soccer", "volleyball"}


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_stats(body: StatRecord, coach: dict = Depends(get_current_coach)):
    """Record player stats for a game or practice session."""
    if body.sport not in VALID_SPORTS:
        raise HTTPException(
            status_code=400,
            detail=f"Sport must be one of: {', '.join(VALID_SPORTS)}",
        )

    # Verify player exists
    player_result = get_table("players").select("id").eq("id", body.player_id).execute()
    if not player_result.data:
        raise HTTPException(status_code=404, detail="Player not found")

    # Verify game if provided
    if body.game_id:
        game_result = get_table("games").select("id").eq("id", body.game_id).execute()
        if not game_result.data:
            raise HTTPException(status_code=404, detail="Game not found")

    payload = {
        "player_id": body.player_id,
        "game_id": body.game_id,
        "sport": body.sport,
        "stats": body.stats,
    }

    result = get_table("player_stats").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to record stats")
    return result.data[0]


@router.get("/player/{player_id}")
async def get_player_stat_history(
    player_id: str, coach: dict = Depends(get_current_coach)
):
    """Full stat history for a player."""
    player_result = get_table("players").select("*").eq("id", player_id).execute()
    if not player_result.data:
        raise HTTPException(status_code=404, detail="Player not found")

    stats_result = (
        get_table("player_stats")
        .select("*")
        .eq("player_id", player_id)
        .order("recorded_at", desc=True)
        .execute()
    )

    return {
        "player": player_result.data[0],
        "stat_records": stats_result.data,
        "total_records": len(stats_result.data),
    }


@router.get("/team/{team_id}/season")
async def get_team_season_stats(
    team_id: str, coach: dict = Depends(get_current_coach)
):
    """Aggregated season stats for all players on a team."""
    team_result = get_table("teams").select("*").eq("id", team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    players_result = (
        get_table("players")
        .select("id, name, jersey_number, position, status")
        .eq("team_id", team_id)
        .execute()
    )
    players = players_result.data
    player_ids = [p["id"] for p in players]

    if not player_ids:
        return {"team": team_result.data[0], "season_stats": [], "total_players": 0}

    stats_result = (
        get_table("player_stats")
        .select("*")
        .in_("player_id", player_ids)
        .order("recorded_at", desc=True)
        .execute()
    )

    # Group and aggregate stats per player
    player_map = {p["id"]: p for p in players}
    aggregated: dict = {}

    for stat in stats_result.data:
        pid = stat["player_id"]
        if pid not in aggregated:
            aggregated[pid] = {
                "player": player_map[pid],
                "games_played": 0,
                "stat_entries": 0,
                "aggregated_stats": {},
            }
        agg = aggregated[pid]
        if stat.get("game_id"):
            agg["games_played"] += 1
        agg["stat_entries"] += 1

        # Sum numeric stats
        for key, val in stat["stats"].items():
            if isinstance(val, (int, float)):
                agg["aggregated_stats"][key] = agg["aggregated_stats"].get(key, 0) + val

    return {
        "team": team_result.data[0],
        "season_stats": list(aggregated.values()),
        "total_players": len(players),
    }


@router.post("/ai-analysis")
async def ai_stat_analysis(
    body: AIAnalysisRequest, coach: dict = Depends(get_current_coach)
):
    """Use Claude to analyze a player's stat history and return insights."""
    player_result = get_table("players").select("*").eq("id", body.player_id).execute()
    if not player_result.data:
        raise HTTPException(status_code=404, detail="Player not found")

    player = player_result.data[0]

    stats_result = (
        get_table("player_stats")
        .select("*")
        .eq("player_id", body.player_id)
        .order("recorded_at", desc=True)
        .limit(20)
        .execute()
    )

    stats_data = stats_result.data

    if not stats_data:
        return {
            "player": player,
            "analysis": "No stat data available for this player yet. Record some stats first.",
        }

    stats_summary = json.dumps(stats_data, indent=2, default=str)
    context = body.additional_context or ""

    prompt = f"""You are an expert sports performance analyst. Analyze the following player stat data and provide actionable coaching insights.

Player: {player['name']}
Position: {player.get('position', 'Unknown')}
Status: {player.get('status', 'active')}
{f'Additional context: {context}' if context else ''}

Stat Records (most recent first):
{stats_summary}

Please provide:
1. **Performance Summary** - Key trends and patterns in the stats
2. **Strengths** - Areas where the player excels
3. **Areas for Improvement** - Specific weaknesses to address in practice
4. **Coaching Recommendations** - 3-5 concrete actions the coach should take
5. **Game Readiness** - Assessment of current form and readiness

Keep your analysis concise, specific, and actionable for a coaching staff."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    analysis_text = message.content[0].text if message.content else "Unable to generate analysis."

    return {
        "player": player,
        "stat_records_analyzed": len(stats_data),
        "analysis": analysis_text,
    }
