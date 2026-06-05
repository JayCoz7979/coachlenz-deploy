import asyncio
import logging
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.organization import Organization
from backend.models.survey import SurveyPrompt, SurveyResponse
from sqlalchemy import select

logger = logging.getLogger(__name__)

ELIGIBLE_TIERS = {"athletic_dept", "district"}

class SurveyWorker(BaseWorker):
    job_type = "survey"

    async def handle(self, payload: dict) -> dict:
        org_id = payload.get("org_id")
        if not org_id:
            return {}
        async with AsyncSessionLocal() as db:
            org_result = await db.execute(select(Organization).where(Organization.id == org_id))
            org = org_result.scalar_one_or_none()
            if not org or org.subscription_tier not in ELIGIBLE_TIERS:
                return {"skipped": True}
            prompts_result = await db.execute(select(SurveyPrompt).where(SurveyPrompt.is_active == True))
            prompts = prompts_result.scalars().all()
        return {"org_id": org_id, "prompts_available": len(prompts)}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(SurveyWorker().run_forever())
