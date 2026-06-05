import asyncio
import logging
from datetime import datetime
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.organization import Organization
from backend.models.user import User
from backend.services.email_service import send_trial_ending_email
from backend.services.trial import is_trial_active, get_trial_days_remaining
from sqlalchemy import select

logger = logging.getLogger(__name__)

class DripWorker(BaseWorker):
    job_type = "drip_email"

    async def handle(self, payload: dict) -> dict:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Organization).where(Organization.is_trial == True))
            orgs = result.scalars().all()
            sent = 0
            for org in orgs:
                if not is_trial_active(org):
                    continue
                days = get_trial_days_remaining(org)
                if days in (7, 3, 1):
                    owner = await db.execute(select(User).where(User.organization_id == org.id, User.role == "owner"))
                    owner = owner.scalar_one_or_none()
                    if owner:
                        try:
                            await send_trial_ending_email(owner.email, owner.name, days)
                            sent += 1
                        except Exception as e:
                            logger.error(f"Drip email failed for {org.id}: {e}")
        return {"emails_sent": sent}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(DripWorker().run_forever())
