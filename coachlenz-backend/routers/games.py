from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from lib.supabase_client import get_table
from lib.auth import get_current_coach

router = APIRouter(prefix="/games", tags=["games"])


class GameCreate(BaseModel):
    team_id: str
    opponent: str
    date: str  # ISO datetime string
    location: Optional[str] = None
    home_away: str = "home"
    notes: Optional[str] = None


class GameUpdate(BaseModel):
    opponent: Optional[str] = None
    date: Optional[str] = None
    location: Optional[str] = None
    home_away: Optional[str] = None
    notes: Optional[str] = None


class ScoreUpdate(BaseModel):
    our_score: int
    opponent_score: int


@router.get("")
async def list_games(
    team_id: Optional[str] = None,
    coach: dict = Depends(get_current_coach),
):
    query = get_table("games").select("*").order("date")
    if team_id:
        query = query.eq("team_id", team_id)
    result = query.execute()
    return result.data


@router.get("/{game_id}")
async def get_game(game_id: str, coach: dict = Depends(get_current_coach)):
    result = get_table("games").select("*").eq("id", game_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Game not found")
    return result.data[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_game(body: GameCreate, coach: dict = Depends(get_current_coach)):
    if body.home_away not in ("home", "away", "neutral"):
        raise HTTPException(status_code=400, detail="home_away must be home, away, or neutral")

    # Verify team exists
    team_result = get_table("teams").select("id").eq("id", body.team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    result = get_table("games").insert(body.model_dump()).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create game")
    return result.data[0]


@router.patch("/{game_id}")
async def update_game(
    game_id: str, body: GameUpdate, coach: dict = Depends(get_current_coach)
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "home_away" in updates and updates["home_away"] not in ("home", "away", "neutral"):
        raise HTTPException(status_code=400, detail="home_away must be home, away, or neutral")

    result = get_table("games").update(updates).eq("id", game_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Game not found")
    return result.data[0]


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(game_id: str, coach: dict = Depends(get_current_coach)):
    get_table("games").delete().eq("id", game_id).execute()


@router.patch("/{game_id}/score")
async def update_score(
    game_id: str, body: ScoreUpdate, coach: dict = Depends(get_current_coach)
):
    """Record final score and calculate result (win/loss/tie)."""
    if body.our_score > body.opponent_score:
        result_val = "win"
    elif body.our_score < body.opponent_score:
        result_val = "loss"
    else:
        result_val = "tie"

    updates = {
        "our_score": body.our_score,
        "opponent_score": body.opponent_score,
        "result": result_val,
    }

    result = get_table("games").update(updates).eq("id", game_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Game not found")
    return result.data[0]


@router.get("/{game_id}/stats")
async def get_game_stats(game_id: str, coach: dict = Depends(get_current_coach)):
    """All player stats recorded for this game."""
    game_result = get_table("games").select("*").eq("id", game_id).execute()
    if not game_result.data:
        raise HTTPException(status_code=404, detail="Game not found")

    stats_result = (
        get_table("player_stats")
        .select("*, players(name, jersey_number, position)")
        .eq("game_id", game_id)
        .execute()
    )

    return {
        "game": game_result.data[0],
        "player_stats": stats_result.data,
    }
