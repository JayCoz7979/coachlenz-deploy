import asyncio
import logging
import subprocess
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.game import Game
from backend.services.r2 import generate_presigned_download_url
from sqlalchemy import select, update

logger = logging.getLogger(__name__)

class IngestWorker(BaseWorker):
    job_type = "ingest"

    async def handle(self, payload: dict) -> dict:
        game_id = payload["game_id"]
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            if not game.r2_key:
                raise ValueError("Game has no R2 key")

        download_url = generate_presigned_download_url(game.r2_key, expires_in=3600)
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", download_url],
                capture_output=True, text=True, timeout=60
            )
            import json
            info = json.loads(probe.stdout)
            duration = float(info.get("format", {}).get("duration", 0))
        except Exception:
            duration = 0

        async with AsyncSessionLocal() as db:
            await db.execute(update(Game).where(Game.id == game_id).values(
                status="ready",
                duration_seconds=int(duration),
            ))
            await db.commit()

        return {"game_id": game_id, "duration_seconds": int(duration)}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(IngestWorker().run_forever())
