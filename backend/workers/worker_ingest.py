import asyncio
import logging
import os
import subprocess
import tempfile
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.game import Game
from backend.models.job import Job
from backend.services.r2 import generate_presigned_download_url, save_local_file, _use_local
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


class IngestWorker(BaseWorker):
    job_type = "ingest"

    async def handle(self, payload: dict) -> dict:
        game_id = payload["game_id"]
        source_url = payload.get("source_url")

        if source_url:
            return await self._ingest_from_url(game_id, source_url, payload.get("source_type", "generic"))
        else:
            return await self._ingest_uploaded_file(game_id)

    async def _ingest_uploaded_file(self, game_id: str) -> dict:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            if not game.r2_key:
                raise ValueError("Game has no R2 key — upload may not be complete yet")

        download_url = generate_presigned_download_url(game.r2_key, expires_in=3600)
        duration = self._probe_duration(download_url)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Game).where(Game.id == game_id).values(
                    status="ready",
                    duration_seconds=int(duration),
                )
            )
            await db.commit()

        return {"game_id": game_id, "duration_seconds": int(duration)}

    async def _ingest_from_url(self, game_id: str, source_url: str, source_type: str) -> dict:
        logger.info(f"[ingest] downloading {source_type} for game {game_id}")

        async with AsyncSessionLocal() as db:
            await db.execute(update(Game).where(Game.id == game_id).values(status="downloading"))
            await db.commit()

        # Dropbox: force direct download
        if source_type == "dropbox":
            source_url = source_url.replace("?dl=0", "?dl=1").replace("www.dropbox.com", "dl.dropboxusercontent.com")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_template = os.path.join(tmpdir, "video.%(ext)s")

            yt_dlp_cmd = [
                "yt-dlp",
                "--no-playlist",
                "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--output", out_template,
                "--no-warnings",
                "--quiet",
                source_url,
            ]

            try:
                proc = subprocess.run(yt_dlp_cmd, capture_output=True, text=True, timeout=1800)
            except subprocess.TimeoutExpired:
                raise ValueError("Download timed out after 30 minutes")

            if proc.returncode != 0:
                error_detail = (proc.stderr or proc.stdout or "unknown error").strip()
                raise ValueError(f"Download failed: {error_detail[:400]}")

            video_file = None
            for fname in os.listdir(tmpdir):
                if fname.startswith("video."):
                    video_file = os.path.join(tmpdir, fname)
                    break

            if not video_file:
                raise ValueError("yt-dlp completed but produced no output file")

            file_size = os.path.getsize(video_file)
            ext = os.path.splitext(video_file)[1] or ".mp4"
            r2_key = f"games/{game_id}/film{ext}"

            duration = self._probe_duration(video_file)

            logger.info(f"[ingest] uploading {file_size} bytes for game {game_id}")
            async with AsyncSessionLocal() as db:
                await db.execute(update(Game).where(Game.id == game_id).values(status="processing"))
                await db.commit()

            if _use_local():
                with open(video_file, "rb") as f:
                    save_local_file(r2_key, f.read())
            else:
                import boto3
                from botocore.config import Config
                from backend.config import settings as cfg
                s3 = boto3.client(
                    "s3",
                    endpoint_url=f"https://{cfg.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                    aws_access_key_id=cfg.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=cfg.R2_SECRET_ACCESS_KEY,
                    config=Config(signature_version="s3v4"),
                    region_name="auto",
                )
                s3.upload_file(video_file, cfg.R2_BUCKET_NAME, r2_key)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Game).where(Game.id == game_id).values(
                    status="ready",
                    r2_key=r2_key,
                    file_size_bytes=file_size,
                    duration_seconds=int(duration),
                )
            )
            await db.commit()

        # Auto-queue AI play detection now that the film is ready
        await self._queue_ai_detect(game_id)

        logger.info(f"[ingest] game {game_id} ready, duration={int(duration)}s")
        return {"game_id": game_id, "duration_seconds": int(duration), "source_type": source_type}

    async def _queue_ai_detect(self, game_id: str) -> None:
        from backend.config import settings as cfg
        if not cfg.ANTHROPIC_API_KEY:
            logger.info(f"[ingest] skipping auto-detect for {game_id}: ANTHROPIC_API_KEY not set")
            return
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                return
            job = Job(
                organization_id=game.organization_id,
                job_type="ai_detect",
                payload={"game_id": game_id},
            )
            db.add(job)
            await db.commit()
        logger.info(f"[ingest] auto-detect job queued for game {game_id}")

    def _probe_duration(self, path_or_url: str) -> float:
        try:
            import json
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path_or_url],
                capture_output=True, text=True, timeout=60,
            )
            info = json.loads(probe.stdout)
            return float(info.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(IngestWorker().run_forever())
