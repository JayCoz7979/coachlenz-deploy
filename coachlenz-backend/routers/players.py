from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from lib.supabase_client import get_table
from lib.auth import get_current_coach

router = APIRouter(prefix="/players", tags=["players"])


class PlayerCreate(BaseModel):
    team_id: str
    name: str
    jersey_number: Optional[str] = None
    position: Optional[str] = None
    grade_year: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str = "active"


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    jersey_number: Optional[str] = None
    position: Optional[str] = None
    grade_year: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


@router.get("")
async def list_players(
    team_id: Optional[str] = None,
    coach: dict = Depends(get_current_coach),
):
    query = get_table("players").select("*").order("name")
    if team_id:
        query = query.eq("team_id", team_id)
    result = query.execute()
    return result.data


@router.get("/{player_id}")
async def get_player(player_id: str, coach: dict = Depends(get_current_coach)):
    result = get_table("players").select("*").eq("id", player_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Player not found")
    return result.data[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_player(body: PlayerCreate, coach: dict = Depends(get_current_coach)):
    if body.status not in ("active", "injured", "inactive"):
        raise HTTPException(status_code=400, detail="Status must be active, injured, or inactive")

    # Verify team exists
    team_result = get_table("teams").select("id").eq("id", body.team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    result = get_table("players").insert(body.model_dump()).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create player")
    return result.data[0]


@router.patch("/{player_id}")
async def update_player(
    player_id: str, body: PlayerUpdate, coach: dict = Depends(get_current_coach)
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "status" in updates and updates["status"] not in ("active", "injured", "inactive"):
        raise HTTPException(status_code=400, detail="Status must be active, injured, or inactive")

    result = get_table("players").update(updates).eq("id", player_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Player not found")
    return result.data[0]


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(player_id: str, coach: dict = Depends(get_current_coach)):
    get_table("players").delete().eq("id", player_id).execute()


@router.get("/{player_id}/stats")
async def get_player_stats(player_id: str, coach: dict = Depends(get_current_coach)):
    # Verify player exists
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
        "stats": stats_result.data,
    }


@router.patch("/{player_id}/status")
async def update_player_status(
    player_id: str, body: StatusUpdate, coach: dict = Depends(get_current_coach)
):
    if body.status not in ("active", "injured", "inactive"):
        raise HTTPException(
            status_code=400,
            detail="Status must be one of: active, injured, inactive",
        )

    result = (
        get_table("players")
        .update({"status": body.status})
        .eq("id", player_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Player not found")
    return result.data[0]
