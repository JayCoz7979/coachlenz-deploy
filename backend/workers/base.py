import asyncio
import logging
import socket
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.models.base import AsyncSessionLocal
from backend.models.job import Job

logger = logging.getLogger(__name__)

WORKER_ID = socket.gethostname()
STUCK_THRESHOLD_MINUTES = 10  # re-queue jobs orphaned by a worker restart within 10 min
MAX_ATTEMPTS = 3              # dead-letter after this many tries so a job that keeps
                             # killing the worker (e.g. an OOM film) can't crash-loop forever

class BaseWorker:
    job_type: str

    async def run_forever(self):
        logger.info(f"[{self.job_type}] worker starting")
        asyncio.create_task(self._watchdog())
        while True:
            try:
                await self._process_one()
            except Exception as e:
                logger.error(f"[{self.job_type}] error: {e}")
            await asyncio.sleep(5)

    async def _process_one(self):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Job)
                .where(Job.job_type == self.job_type, Job.status == "queued")
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            job = result.scalar_one_or_none()
            if not job:
                return
            job.attempts += 1
            # Circuit breaker: a job that keeps dying (OOM, corrupt film) is left
            # "running" and re-queued by the watchdog forever. Give up after
            # MAX_ATTEMPTS so it can't crash-loop the shared worker or burn cost.
            if job.attempts > MAX_ATTEMPTS:
                job.status = "error"
                job.error_message = f"Gave up after {MAX_ATTEMPTS} failed attempts (job kept failing)."
                job.locked_at = None
                await db.commit()
                logger.error(f"[{self.job_type}] job {job.id} dead-lettered after {MAX_ATTEMPTS} attempts")
                return
            job.status = "running"
            job.locked_at = datetime.utcnow()
            job.locked_by = WORKER_ID
            await db.commit()

        try:
            # Correlate any agent logs emitted during this run with the job (UATP audit trail).
            payload = dict(job.payload or {})
            payload["_job_id"] = str(job.id)
            result = await self.handle(payload)
            async with AsyncSessionLocal() as db:
                await db.execute(update(Job).where(Job.id == job.id).values(status="done", result=result or {}, locked_at=None))
                await db.commit()
        except Exception as e:
            logger.error(f"[{self.job_type}] job {job.id} failed: {e}")
            async with AsyncSessionLocal() as db:
                await db.execute(update(Job).where(Job.id == job.id).values(status="error", error_message=str(e), locked_at=None))
                await db.commit()

    async def _watchdog(self):
        while True:
            await asyncio.sleep(60)
            try:
                cutoff = datetime.utcnow() - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Job)
                        .where(Job.job_type == self.job_type, Job.status == "running", Job.locked_at < cutoff)
                        .values(status="queued", locked_at=None, locked_by=None)
                    )
                    await db.commit()
            except Exception as e:
                logger.error(f"[{self.job_type}] watchdog error: {e}")

    async def handle(self, payload: dict) -> dict:
        raise NotImplementedError
