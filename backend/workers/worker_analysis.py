import asyncio
import logging
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.game import Game
from backend.models.event import Event
from sqlalchemy import select

logger = logging.getLogger(__name__)

class AnalysisWorker(BaseWorker):
    job_type = "analysis"

    async def handle(self, payload: dict) -> dict:
        game_id = payload["game_id"]
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            events = await db.execute(select(Event).where(Event.game_id == game_id))
            event_count = len(events.scalars().all())
        return {"game_id": game_id, "events_found": event_count}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(AnalysisWorker().run_forever())
