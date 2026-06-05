import asyncio
import logging
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.comms import FilmPackage
from backend.services.r2 import generate_presigned_download_url
from sqlalchemy import select

logger = logging.getLogger(__name__)

class PackagesWorker(BaseWorker):
    job_type = "package"

    async def handle(self, payload: dict) -> dict:
        package_id = payload["package_id"]
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(FilmPackage).where(FilmPackage.id == package_id))
            pkg = result.scalar_one_or_none()
            if not pkg:
                raise ValueError(f"Package {package_id} not found")
        return {"package_id": package_id, "clip_count": len(pkg.clip_ids or [])}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(PackagesWorker().run_forever())
