from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, List
from lib.supabase_client import get_table
from lib.auth import get_current_coach

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamCreate(BaseModel):
    name: str
    sport: str
    season: Optional[str] = None
    head_coach: Optional[str] = None
    school: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    sport: Optional[str] = None
    season: Optional[str] = None
    head_coach: Optional[str] = None
    school: Optional[str] = None


VALID_SPORTS = {"football", "basketball", "baseball", "softball", "soccer", "volleyball"}


@router.get("")
async def list_teams(coach: dict = Depends(get_current_coach)):
    result = get_table("teams").select("*").order("created_at", desc=True).execute()
    return result.data


@router.get("/{team_id}")
async def get_team(team_id: str, coach: dict = Depends(get_current_coach)):
    result = get_table("teams").select("*").eq("id", team_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Team not found")
    return result.data[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(body: TeamCreate, coach: dict = Depends(get_current_coach)):
    if body.sport not in VALID_SPORTS:
        raise HTTPException(
            status_code=400,
            detail=f"Sport must be one of: {', '.join(VALID_SPORTS)}",
        )
    result = get_table("teams").insert(body.model_dump()).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create team")
    return result.data[0]


@router.patch("/{team_id}")
async def update_team(
    team_id: str, body: TeamUpdate, coach: dict = Depends(get_current_coach)
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "sport" in updates and updates["sport"] not in VALID_SPORTS:
        raise HTTPException(
            status_code=400,
            detail=f"Sport must be one of: {', '.join(VALID_SPORTS)}",
        )

    result = get_table("teams").update(updates).eq("id", team_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Team not found")
    return result.data[0]


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: str, coach: dict = Depends(get_current_coach)):
    get_table("teams").delete().eq("id", team_id).execute()


@router.get("/{team_id}/roster")
async def get_team_roster(team_id: str, coach: dict = Depends(get_current_coach)):
    # Verify team exists
    team_result = get_table("teams").select("id").eq("id", team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    result = (
        get_table("players")
        .select("*")
        .eq("team_id", team_id)
        .order("name")
        .execute()
    )
    return result.data


@router.get("/{team_id}/schedule")
async def get_team_schedule(team_id: str, coach: dict = Depends(get_current_coach)):
    team_result = get_table("teams").select("id").eq("id", team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    result = (
        get_table("games")
        .select("*")
        .eq("team_id", team_id)
        .order("date")
        .execute()
    )
    return result.data


@router.get("/{team_id}/stats")
async def get_team_stats(team_id: str, coach: dict = Depends(get_current_coach)):
    """Aggregate player stats for all players on the team."""
    team_result = get_table("teams").select("id, sport").eq("id", team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get all player IDs for this team
    players_result = (
        get_table("players").select("id, name, jersey_number, position").eq("team_id", team_id).execute()
    )
    players = players_result.data
    player_ids = [p["id"] for p in players]

    if not player_ids:
        return {"team_id": team_id, "players": [], "stats": []}

    # Get stats for all players
    stats_result = (
        get_table("player_stats")
        .select("*")
        .in_("player_id", player_ids)
        .execute()
    )

    # Group stats by player
    player_map = {p["id"]: p for p in players}
    stats_by_player: dict = {}
    for stat in stats_result.data:
        pid = stat["player_id"]
        if pid not in stats_by_player:
            stats_by_player[pid] = {
                "player": player_map.get(pid, {}),
                "stat_records": [],
            }
        stats_by_player[pid]["stat_records"].append(stat)

    return {
        "team_id": team_id,
        "players": players,
        "stats_by_player": list(stats_by_player.values()),
    }
