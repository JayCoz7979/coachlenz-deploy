from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.survey import SurveyPrompt, SurveyResponse
from backend.services.auth import get_current_user, get_current_org

router = APIRouter(prefix="/survey", tags=["survey"])

ELIGIBLE_TIERS = {"athletic_dept", "district"}

class SurveyResponseCreate(BaseModel):
    prompt_id: str
    response_text: Optional[str] = None
    response_rating: Optional[int] = None
    response_choice: Optional[str] = None

@router.get("/prompts")
async def get_prompts(user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if org.subscription_tier not in ELIGIBLE_TIERS:
        raise HTTPException(status_code=403, detail="Survey not available on this plan")
    result = await db.execute(select(SurveyPrompt).where(SurveyPrompt.is_active == True).order_by(SurveyPrompt.display_order))
    prompts = result.scalars().all()
    return [{"id": str(p.id), "question": p.question, "response_type": p.response_type, "options": p.options} for p in prompts]

@router.post("/respond")
async def submit_response(body: SurveyResponseCreate, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    if org.subscription_tier not in ELIGIBLE_TIERS:
        raise HTTPException(status_code=403, detail="Survey not available on this plan")
    response = SurveyResponse(organization_id=org.id, user_id=user.id, **body.dict())
    db.add(response)
    await db.commit()
    return {"ok": True}
