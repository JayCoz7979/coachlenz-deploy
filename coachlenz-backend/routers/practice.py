import os
import json
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, Any, List
import anthropic
from lib.supabase_client import get_table
from lib.auth import get_current_coach
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/practice", tags=["practice"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class PracticePlanCreate(BaseModel):
    team_id: str
    date: str  # YYYY-MM-DD
    title: str
    duration_minutes: Optional[int] = None
    drills: List[Any] = []
    notes: Optional[str] = None


class PracticePlanUpdate(BaseModel):
    date: Optional[str] = None
    title: Optional[str] = None
    duration_minutes: Optional[int] = None
    drills: Optional[List[Any]] = None
    notes: Optional[str] = None


class GeneratePlanRequest(BaseModel):
    team_id: str
    sport: str
    focus_areas: List[str]
    duration_minutes: int = 90
    player_count: Optional[int] = None
    notes: Optional[str] = None


@router.get("")
async def list_practice_plans(
    team_id: Optional[str] = None,
    coach: dict = Depends(get_current_coach),
):
    query = get_table("practice_plans").select("*").order("date", desc=True)
    if team_id:
        query = query.eq("team_id", team_id)
    result = query.execute()
    return result.data


@router.get("/team/{team_id}")
async def get_team_practice_plans(
    team_id: str, coach: dict = Depends(get_current_coach)
):
    """Upcoming practice plans for a team."""
    from datetime import date

    today = date.today().isoformat()

    result = (
        get_table("practice_plans")
        .select("*")
        .eq("team_id", team_id)
        .gte("date", today)
        .order("date")
        .execute()
    )
    return result.data


@router.get("/{plan_id}")
async def get_practice_plan(plan_id: str, coach: dict = Depends(get_current_coach)):
    result = get_table("practice_plans").select("*").eq("id", plan_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Practice plan not found")
    return result.data[0]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_practice_plan(
    body: PracticePlanCreate, coach: dict = Depends(get_current_coach)
):
    team_result = get_table("teams").select("id").eq("id", body.team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    result = get_table("practice_plans").insert(body.model_dump()).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create practice plan")
    return result.data[0]


@router.patch("/{plan_id}")
async def update_practice_plan(
    plan_id: str, body: PracticePlanUpdate, coach: dict = Depends(get_current_coach)
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = get_table("practice_plans").update(updates).eq("id", plan_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Practice plan not found")
    return result.data[0]


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_practice_plan(
    plan_id: str, coach: dict = Depends(get_current_coach)
):
    get_table("practice_plans").delete().eq("id", plan_id).execute()


@router.post("/generate")
async def generate_practice_plan(
    body: GeneratePlanRequest, coach: dict = Depends(get_current_coach)
):
    """Use Claude to generate a practice plan and save it."""
    team_result = get_table("teams").select("*").eq("id", body.team_id).execute()
    if not team_result.data:
        raise HTTPException(status_code=404, detail="Team not found")

    team = team_result.data[0]
    focus_str = ", ".join(body.focus_areas) if body.focus_areas else "general skills"
    player_str = f"{body.player_count} players" if body.player_count else "a team"
    context = body.notes or ""

    prompt = f"""You are an expert sports coach helping design a practice plan for {player_str}.

Sport: {body.sport}
Team: {team['name']}
Duration: {body.duration_minutes} minutes
Focus Areas: {focus_str}
{f'Additional notes: {context}' if context else ''}

Generate a detailed practice plan with specific drills. Return your response as a valid JSON object with this exact structure:
{{
  "title": "Practice plan title",
  "drills": [
    {{
      "name": "Drill name",
      "duration_minutes": 10,
      "description": "How to run the drill",
      "equipment": ["item1", "item2"],
      "focus": "What skill this targets",
      "players_needed": "all" or number,
      "intensity": "low" or "medium" or "high"
    }}
  ],
  "warmup_minutes": 10,
  "cooldown_minutes": 5,
  "coaching_notes": "Key points to emphasize today"
}}

Make the drills specific to {body.sport} and the stated focus areas. Ensure total drill time fits within {body.duration_minutes} minutes including warmup and cooldown."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = message.content[0].text if message.content else "{}"

    # Try to parse the JSON response
    try:
        # Strip markdown code blocks if present
        clean = raw_text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        plan_data = json.loads(clean)
    except json.JSONDecodeError:
        # Return as unstructured if parse fails
        return {
            "generated": True,
            "raw_response": raw_text,
            "error": "Could not parse structured response — use raw_response to manually create plan",
        }

    from datetime import date, timedelta

    next_practice_date = (date.today() + timedelta(days=1)).isoformat()

    new_plan = {
        "team_id": body.team_id,
        "date": next_practice_date,
        "title": plan_data.get("title", f"{body.sport.title()} Practice — {focus_str}"),
        "duration_minutes": body.duration_minutes,
        "drills": plan_data.get("drills", []),
        "notes": plan_data.get("coaching_notes", ""),
    }

    result = get_table("practice_plans").insert(new_plan).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save generated plan")

    return {
        "generated": True,
        "plan": result.data[0],
        "ai_notes": plan_data.get("coaching_notes", ""),
    }
