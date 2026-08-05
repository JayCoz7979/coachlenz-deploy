import asyncio
import logging
import socket
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.models.base import AsyncSessionLocal
from backend.models.job import Job
from backend.observability import init_sentry, capture

logger = logging.getLogger(__name__)

WORKER_ID = socket.gethostname()
STUCK_THRESHOLD_MINUTES = 10  # re-queue jobs orphaned by a worker restart within 10 min
HEARTBEAT_SECONDS = 120       # refresh a running job's lock this often so a legitimately
                              # long job (full-game detection runs 15-20 min) is NOT re-queued
                              # by the watchdog and double-executed. A dead worker stops
                              # heartbeating and is still reclaimed after STUCK_THRESHOLD.
MAX_ATTEMPTS = 3              # dead-letter after this many tries so a job that keeps
                             # killing the worker (e.g. an OOM film) can't crash-loop forever

class BaseWorker:
    job_type: str
    # How long a "running" job may go without a heartbeat before the watchdog re-queues
    # it as orphaned. Default is conservative for long, possibly non-idempotent jobs
    # (detection/ingest). A short, idempotent job (reports) overrides this lower so an
    # orphaned run recovers in minutes, not ~10.
    stuck_threshold_minutes: int = STUCK_THRESHOLD_MINUTES

    async def run_forever(self):
        # Workers run as their own processes and never import main.py, so this is
        # where their Sentry gets initialized (no-op in-API / without SENTRY_DSN).
        init_sentry(f"worker:{self.job_type}")
        logger.info(f"[{self.job_type}] worker starting")
        asyncio.create_task(self._watchdog())
        while True:
            try:
                await self._process_one()
            except Exception as e:
                logger.error(f"[{self.job_type}] error: {e}")
                capture(e, worker=self.job_type, phase="process_loop")
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
                dead_payload = dict(job.payload or {})
                dead_payload["_job_id"] = str(job.id)  # let on_dead_letter reverse job-linked side effects (e.g. usage refund)
                dead_reason = job.error_message
                await db.commit()
                logger.error(f"[{self.job_type}] job {job.id} dead-lettered after {MAX_ATTEMPTS} attempts")
                # Tell the domain object it failed (e.g. mark the report failed) so the
                # UI stops spinning — the worker may have died before handle() could.
                try:
                    await self.on_dead_letter(dead_payload, dead_reason)
                except Exception as e:
                    logger.error(f"[{self.job_type}] on_dead_letter failed: {e}")
                    capture(e, worker=self.job_type, phase="on_dead_letter")
                return
            job.status = "running"
            job.locked_at = datetime.utcnow()
            job.locked_by = WORKER_ID
            await db.commit()

        job_id = job.id
        stop = asyncio.Event()

        async def _heartbeat():
            # Keep locked_at fresh while handle() runs so the watchdog does not
            # re-queue (and thus double-run) a legitimately long job.
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    pass
                if stop.is_set():
                    break
                try:
                    async with AsyncSessionLocal() as db:
                        await db.execute(update(Job).where(Job.id == job_id, Job.status == "running")
                                         .values(locked_at=datetime.utcnow()))
                        await db.commit()
                except Exception:
                    pass

        hb = asyncio.create_task(_heartbeat())
        try:
            # Correlate any agent logs emitted during this run with the job (UATP audit trail).
            payload = dict(job.payload or {})
            payload["_job_id"] = str(job_id)
            result = await self.handle(payload)
            async with AsyncSessionLocal() as db:
                await db.execute(update(Job).where(Job.id == job_id).values(status="done", result=result or {}, locked_at=None))
                await db.commit()
        except Exception as e:
            logger.error(f"[{self.job_type}] job {job_id} failed: {e}")
            capture(e, worker=self.job_type, job_id=str(job_id), phase="handle")
            async with AsyncSessionLocal() as db:
                await db.execute(update(Job).where(Job.id == job_id).values(status="error", error_message=str(e), locked_at=None))
                await db.commit()
        finally:
            stop.set()
            hb.cancel()

    async def _watchdog(self):
        # Sweep once immediately on start (so a redeploy reclaims already-stale jobs
        # without waiting a full cycle), then every 60s.
        while True:
            try:
                cutoff = datetime.utcnow() - timedelta(minutes=self.stuck_threshold_minutes)
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Job)
                        .where(Job.job_type == self.job_type, Job.status == "running", Job.locked_at < cutoff)
                        .values(status="queued", locked_at=None, locked_by=None)
                    )
                    await db.commit()
            except Exception as e:
                logger.error(f"[{self.job_type}] watchdog error: {e}")
                capture(e, worker=self.job_type, phase="watchdog")
            await asyncio.sleep(60)

    async def on_dead_letter(self, payload: dict, reason: str) -> None:
        """Called when a job is given up on (dead-lettered) after MAX_ATTEMPTS. Default
        no-op; a worker overrides this to record the failure on its domain object (e.g.
        mark the report failed) so a user isn't left staring at an infinite spinner."""
        return None

    async def handle(self, payload: dict) -> dict:
        raise NotImplementedError
