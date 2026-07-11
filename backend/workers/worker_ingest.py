import asyncio
import logging
import os
import signal
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
        try:
            return await self._ingest_uploaded_file_inner(game_id)
        except Exception as e:
            # Mirror the URL path: a corrupt upload or ffprobe failure must not
            # leave the game stuck mid-processing with nothing shown to the coach.
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Game).where(Game.id == game_id).values(
                        status="error", error_message=str(e)[:480]
                    )
                )
                await db.commit()
            raise

    async def _ingest_uploaded_file_inner(self, game_id: str) -> dict:
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
            # Auto-chain detection so an uploaded game analyzes itself end-to-end
            # (upload -> ingest -> ready -> multi-pass detection) with no extra click.
            db.add(Job(
                organization_id=game.organization_id,
                job_type="ai_detect",
                # Default auto-runs to the cheap single-pass engine; users opt into
                # the 3x-cost deep engine explicitly from the game page.
                payload={"game_id": str(game_id), "dry_run": False, "detection_mode": "fast"},
            ))
            await db.commit()

        return {"game_id": game_id, "duration_seconds": int(duration)}

    async def _ingest_from_url(self, game_id: str, source_url: str, source_type: str) -> dict:
        try:
            return await self._ingest_from_url_inner(game_id, source_url, source_type)
        except Exception as e:
            # Don't leave the game stuck in "downloading" — surface the failure.
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Game).where(Game.id == game_id).values(
                        status="error", error_message=str(e)[:480]
                    )
                )
                await db.commit()
            raise

    async def _ingest_from_url_inner(self, game_id: str, source_url: str, source_type: str) -> dict:
        logger.info(f"[ingest] downloading {source_type} for game {game_id}")

        async with AsyncSessionLocal() as db:
            await db.execute(update(Game).where(Game.id == game_id).values(status="downloading"))
            await db.commit()

        # Dropbox: force direct download
        if source_type == "dropbox":
            source_url = source_url.replace("?dl=0", "?dl=1").replace("www.dropbox.com", "dl.dropboxusercontent.com")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_template = os.path.join(tmpdir, "video.%(ext)s")

            # Optional cookies file (Netscape format) supplied via env to defeat
            # YouTube datacenter-IP gating. Written once per download to tmp.
            cookies_path = None
            cookies_content = os.environ.get("YOUTUBE_COOKIES", "").strip()
            if cookies_content:
                cookies_path = os.path.join(tmpdir, "cookies.txt")
                with open(cookies_path, "w", encoding="utf-8") as cf:
                    cf.write(cookies_content)

            proxy = os.environ.get("YTDLP_PROXY", "").strip()

            base_cmd = [
                "yt-dlp",
                "--no-playlist",
                # Permissive selector: prefer mp4 but fall back to any best video+audio,
                # then any single best stream. Avoids "Requested format is not available".
                "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--output", out_template,
                "--no-warnings",
                "--quiet",
                "--retries", "5",
                "--fragment-retries", "10",
                "--socket-timeout", "30",
            ]
            if proxy:
                base_cmd += ["--proxy", proxy]

            # ── Hudl / NFHS: capture the stream with a headless browser ──────
            # These serve token-gated (non-DRM) HLS/MP4 that yt-dlp can't reach
            # directly. We drive Chromium to load the page, capture the stream
            # URL + session cookies, then download it.
            download_target = source_url
            if source_type in ("hudl", "nfhs"):
                cookies_env = "NFHS_COOKIES" if source_type == "nfhs" else "HUDL_COOKIES"
                logger.info(f"[ingest] capturing {source_type} stream for game {game_id}")

                # Use the org's connected account login, if one exists.
                credentials = None
                try:
                    async with AsyncSessionLocal() as db:
                        from backend.models.source_connection import SourceConnection
                        from backend.services.encryption import decrypt_json
                        gres = await db.execute(select(Game).where(Game.id == game_id))
                        g = gres.scalar_one_or_none()
                        if g:
                            cres = await db.execute(
                                select(SourceConnection).where(
                                    SourceConnection.organization_id == g.organization_id,
                                    SourceConnection.provider == source_type,
                                )
                            )
                            conn = cres.scalar_one_or_none()
                            if conn:
                                credentials = decrypt_json(conn.encrypted_credentials)
                                logger.info(f"[ingest] using connected {source_type} account for capture")
                except Exception as e:
                    logger.warning(f"[ingest] could not load {source_type} connection: {e}")

                from backend.services.hudl_capture import capture_hudl_stream, HudlCaptureError
                try:
                    cap = await capture_hudl_stream(
                        source_url, timeout_s=90, cookies_env=cookies_env,
                        credentials=credentials, provider=source_type,
                    )
                except HudlCaptureError as e:
                    site = "NFHS Network" if source_type == "nfhs" else "Hudl"
                    raise ValueError(
                        f"Could not capture this {site} film: {e}. It likely requires "
                        f"a paid/login account — add your {site} login, or download the "
                        f"film and use Upload File instead."
                    )
                download_target = cap["manifest_url"]
                # Use the session cookies captured from the browser.
                cookies_path = os.path.join(tmpdir, "hudl_cookies.txt")
                with open(cookies_path, "w", encoding="utf-8") as cf:
                    cf.write(cap["cookies"])
                for hk, hv in cap["headers"].items():
                    base_cmd += ["--add-header", f"{hk}:{hv}"]

            if cookies_path:
                base_cmd += ["--cookies", cookies_path]

            # For YouTube, datacenter IPs frequently get "Requested format is not
            # available" because the default web client requires a PO token. We try
            # several player clients that often bypass this. Each attempt is a full
            # download try; we stop at the first success.
            if source_type == "youtube":
                client_attempts = [
                    ["--extractor-args", "youtube:player_client=tv,ios,web_safari"],
                    ["--extractor-args", "youtube:player_client=android,ios"],
                    ["--extractor-args", "youtube:player_client=web_safari"],
                    [],  # plain (works if cookies/proxy are set)
                ]
            else:
                client_attempts = [[]]

            proc = None
            last_error = "unknown error"
            for extra in client_attempts:
                cmd = base_cmd + extra + [download_target]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                except subprocess.TimeoutExpired:
                    raise ValueError("Download timed out after 30 minutes")
                if proc.returncode == 0:
                    break
                last_error = (proc.stderr or proc.stdout or "unknown error").strip()
                logger.warning(f"[ingest] yt-dlp attempt failed ({extra}): {last_error[:200]}")

            if proc is None or proc.returncode != 0:
                raise ValueError(f"Download failed: {last_error[:400]}")

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


async def _run_ingest_and_detect():
    """Run the ingest worker AND the AI detection worker in one process.

    Detection has no dedicated Railway service, and this service already holds the
    exact environment detection needs (ANTHROPIC_API_KEY, R2_*, DATABASE_URL, and
    ffmpeg in the image). Co-locating them here is what makes auto-detect actually
    execute in production. Each worker's run_forever loop isolates its own errors.

    GRACEFUL SHUTDOWN: handle SIGTERM/SIGINT so the container EXITS on deploy. Without
    this the old container ignored SIGTERM, lingered through every rolling deploy, and
    kept grabbing jobs off the queue with stale code — which silently defeated every
    detection fix. Exiting on signal lets Railway swap containers cleanly.
    """
    from backend.workers.worker_ai_detect import AiDetectWorker

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            pass

    tasks = [
        asyncio.create_task(IngestWorker().run_forever()),
        asyncio.create_task(AiDetectWorker().run_forever()),
    ]
    await stop.wait()
    logger.info("[worker] shutdown signal received — exiting cleanly for container swap")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_ingest_and_detect())
