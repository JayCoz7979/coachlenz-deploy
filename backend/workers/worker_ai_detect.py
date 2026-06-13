"""
AI Play Detection Worker
Extracts frames from ingested game film and uses Claude Vision to auto-detect
plays, read scoreboard overlays, identify formations, and create Event records.
"""
import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile
from typing import Optional

from sqlalchemy import select, update

from backend.config import settings
from backend.models.base import AsyncSessionLocal
from backend.models.event import Event
from backend.models.game import Game
from backend.models.job import Job
from backend.services.r2 import generate_presigned_download_url, _use_local, LOCAL_STORE
from backend.workers.base import BaseWorker

logger = logging.getLogger(__name__)

# How many seconds between scene-change frame samples (fallback if scene detection yields too few)
FALLBACK_INTERVAL = 8
# Max frames to send Claude per batch (controls token cost)
FRAMES_PER_BATCH = 5
# Minimum scene-change threshold (0–1). Lower = more sensitive.
SCENE_THRESHOLD = 0.35
# Skip the first N seconds (avoids intro graphics / countdown clocks)
SKIP_START_SECONDS = 5


DETECTION_PROMPT = """You are an expert football film analyst. I am showing you frames extracted from game film.
Your job is to identify each individual play and extract structured data from it.

For EACH distinct play you can identify, return a JSON object in the array. A "play" is any offensive snap — run, pass, screen, draw, QB sneak, punt, field goal, PAT, kickoff, or extra-point attempt.

Skip: timeouts, huddles, sideline shots, commercials, halftime, instant replays, pre-game, post-game.

For each play, extract what you can read from scoreboard overlays OR infer from the field view:
- time_seconds: approximate timestamp in the video (integer, estimate from frame position)
- down: 1, 2, 3, or 4 (null if not visible or not applicable)
- distance: yards to go (null if not visible)
- field_position: e.g. "OWN 32", "OPP 14" (null if not visible)
- formation: offensive formation — "Shotgun", "I-Form", "Pistol", "Singleback", "Wildcat", "Empty", "Trips", "Bunch", "Pro Set", or "Other"
- play_type: "Run", "Pass", "Screen", "Draw", "Option", "RPO", "QB Sneak", "Punt", "Kickoff", "Field Goal", "PAT", or "Other"
- result: "Gain", "Loss", "Incomplete", "Touchdown", "Interception", "Fumble", "Sack", "Penalty", "First Down", "Turnover on Downs", "Made", "Missed", or "Punt"
- yards_gained: integer (positive or negative), null if not determinable
- personnel: offensive personnel grouping if visible — "11", "12", "21", "22", "10", "20", "13", or null
- motion: true if pre-snap motion is visible, false otherwise
- confidence: 0.0–1.0 — how confident you are this is a real play (not a replay, broadcast segment, etc.)

Return ONLY valid JSON in this exact format, nothing else:
{"plays": [{"time_seconds": 0, "down": null, "distance": null, "field_position": null, "formation": null, "play_type": null, "result": null, "yards_gained": null, "personnel": null, "motion": false, "confidence": 0.8}]}

If you see zero plays in these frames, return: {"plays": []}"""


class AiDetectWorker(BaseWorker):
    job_type = "ai_detect"

    async def handle(self, payload: dict) -> dict:
        game_id = payload["game_id"]
        return await self._detect_plays(game_id)

    async def _detect_plays(self, game_id: str) -> dict:
        # ── Load game ──────────────────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            if game.status != "ready":
                raise ValueError(f"Game not ready for detection (status={game.status})")

        # ── Resolve video path / URL ───────────────────────────────────────
        if _use_local():
            video_path = LOCAL_STORE / game.r2_key
            if not video_path.exists():
                raise ValueError(f"Local video file not found: {video_path}")
            video_source = str(video_path)
        else:
            video_source = generate_presigned_download_url(game.r2_key, expires_in=7200)

        # ── Update game status ─────────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            await db.execute(update(Game).where(Game.id == game_id).values(status="analyzing"))
            await db.commit()

        total_plays = 0
        try:
            with tempfile.TemporaryDirectory() as frames_dir:
                # ── Extract frames ─────────────────────────────────────────
                frame_paths = await asyncio.get_event_loop().run_in_executor(
                    None, self._extract_frames, video_source, frames_dir, game.duration_seconds
                )

                if not frame_paths:
                    logger.warning(f"[ai_detect] No frames extracted for game {game_id}")
                    async with AsyncSessionLocal() as db:
                        await db.execute(update(Game).where(Game.id == game_id).values(status="ready"))
                        await db.commit()
                    return {"game_id": game_id, "plays_detected": 0}

                logger.info(f"[ai_detect] Extracted {len(frame_paths)} frames for game {game_id}")

                # ── Send batches to Claude Vision ──────────────────────────
                all_plays = []
                batches = [frame_paths[i:i + FRAMES_PER_BATCH] for i in range(0, len(frame_paths), FRAMES_PER_BATCH)]

                for batch_idx, batch in enumerate(batches):
                    try:
                        plays = await self._analyze_batch(batch, batch_idx, len(batches))
                        all_plays.extend(plays)
                        logger.info(f"[ai_detect] Batch {batch_idx+1}/{len(batches)}: {len(plays)} plays")
                    except Exception as e:
                        logger.warning(f"[ai_detect] Batch {batch_idx+1} failed: {e}")
                        continue

                # ── Deduplicate by time (within 5s = same play) ───────────
                deduped = self._deduplicate_plays(all_plays)
                logger.info(f"[ai_detect] {len(all_plays)} raw → {len(deduped)} after dedup")

                # ── Persist events ─────────────────────────────────────────
                if deduped:
                    async with AsyncSessionLocal() as db:
                        # Load organization_id
                        result = await db.execute(select(Game).where(Game.id == game_id))
                        g = result.scalar_one()
                        org_id = g.organization_id

                        events = [
                            Event(
                                game_id=game_id,
                                organization_id=org_id,
                                event_type="play",
                                time_seconds=p.get("time_seconds"),
                                down=p.get("down"),
                                distance=p.get("distance"),
                                field_position=p.get("field_position"),
                                formation=p.get("formation"),
                                play_type=p.get("play_type"),
                                result=p.get("result"),
                                yards_gained=p.get("yards_gained"),
                                personnel=p.get("personnel"),
                                motion=p.get("motion", False),
                                extra_data={"auto_detected": True, "confidence": p.get("confidence", 0.8)},
                            )
                            for p in deduped
                        ]
                        db.add_all(events)
                        await db.commit()
                        total_plays = len(events)

        finally:
            # Always restore game to ready
            async with AsyncSessionLocal() as db:
                await db.execute(update(Game).where(Game.id == game_id).values(status="ready"))
                await db.commit()

        logger.info(f"[ai_detect] game {game_id}: {total_plays} plays auto-detected")
        return {"game_id": game_id, "plays_detected": total_plays}

    def _extract_frames(self, video_source: str, output_dir: str, duration_seconds: Optional[int]) -> list[str]:
        """
        Extract frames at scene changes using ffmpeg's scene filter.
        Falls back to fixed interval if too few scenes are detected.
        """
        scene_frames_dir = os.path.join(output_dir, "scene")
        os.makedirs(scene_frames_dir, exist_ok=True)

        # Scene-change based extraction
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(SKIP_START_SECONDS),
            "-i", video_source,
            "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
            "-vsync", "vfr",
            "-frame_pts", "1",
            "-q:v", "3",
            "-f", "image2",
            os.path.join(scene_frames_dir, "frame_%06d.jpg"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        scene_frames = sorted(
            [os.path.join(scene_frames_dir, f) for f in os.listdir(scene_frames_dir) if f.endswith(".jpg")]
        )

        # If we got too few scene frames, supplement with fixed-interval frames
        min_expected = max(10, (duration_seconds or 0) // 30)
        if len(scene_frames) < min_expected:
            logger.info(f"[ai_detect] Only {len(scene_frames)} scene frames — adding interval frames")
            interval_dir = os.path.join(output_dir, "interval")
            os.makedirs(interval_dir, exist_ok=True)
            cmd2 = [
                "ffmpeg", "-y",
                "-ss", str(SKIP_START_SECONDS),
                "-i", video_source,
                "-vf", f"fps=1/{FALLBACK_INTERVAL}",
                "-q:v", "3",
                os.path.join(interval_dir, "frame_%06d.jpg"),
            ]
            subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
            interval_frames = sorted(
                [os.path.join(interval_dir, f) for f in os.listdir(interval_dir) if f.endswith(".jpg")]
            )
            # Merge and deduplicate (use all interval frames since scene detection was sparse)
            all_frames = sorted(set(scene_frames + interval_frames))
        else:
            all_frames = scene_frames

        # Cap at 400 frames to keep cost reasonable (~80 API calls)
        if len(all_frames) > 400:
            step = len(all_frames) // 400
            all_frames = all_frames[::step][:400]

        return all_frames

    async def _analyze_batch(self, frame_paths: list[str], batch_idx: int, total_batches: int) -> list[dict]:
        """Send a batch of frames to Claude Vision and parse structured play data."""
        import anthropic

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build image content blocks
        content = []
        for i, path in enumerate(frame_paths):
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            # Approximate timestamp from filename index and batch position
            frame_num = int(os.path.splitext(os.path.basename(path))[0].split("_")[-1])
            approx_time = SKIP_START_SECONDS + frame_num * FALLBACK_INTERVAL
            content.append({
                "type": "text",
                "text": f"Frame {i+1} (approx {approx_time}s into video):"
            })
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": data}
            })

        content.append({"type": "text", "text": DETECTION_PROMPT})

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )

        raw = response.content[0].text.strip()

        # Extract JSON even if Claude wraps it in markdown
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        plays = parsed.get("plays", [])

        # Filter by confidence
        return [p for p in plays if p.get("confidence", 0) >= 0.5]

    def _deduplicate_plays(self, plays: list[dict]) -> list[dict]:
        """Merge plays that are within 5 seconds of each other (likely the same play detected twice)."""
        if not plays:
            return []

        sorted_plays = sorted(plays, key=lambda p: p.get("time_seconds") or 0)
        deduped = [sorted_plays[0]]

        for play in sorted_plays[1:]:
            last_time = deduped[-1].get("time_seconds") or 0
            this_time = play.get("time_seconds") or 0
            if (this_time - last_time) < 5:
                # Keep the one with higher confidence
                if play.get("confidence", 0) > deduped[-1].get("confidence", 0):
                    deduped[-1] = play
            else:
                deduped.append(play)

        return deduped


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(AiDetectWorker().run_forever())
