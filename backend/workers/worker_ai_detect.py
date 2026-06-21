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
import re
import subprocess
import tempfile
from typing import Optional

from sqlalchemy import select, update

from backend.config import settings
from backend.models.base import AsyncSessionLocal
from backend.models.event import Event
from backend.models.game import Game
from backend.models.job import Job
from backend.services.r2 import generate_presigned_download_url, _use_local, LOCAL_STORAGE_DIR
from backend.workers.base import BaseWorker

logger = logging.getLogger(__name__)

# How many seconds between fixed-interval frame samples (tighter = catch more plays)
FALLBACK_INTERVAL = 5
# Max frames to send Claude per batch (controls token cost)
FRAMES_PER_BATCH = 5
# Minimum scene-change threshold (0–1). Lower = more sensitive (catches more snaps).
SCENE_THRESHOLD = 0.27
# Cap on total frames analyzed per game (recall vs cost). ~MAX_FRAMES/5 Claude calls.
MAX_FRAMES = 900
# Skip the first N seconds (avoids intro graphics / countdown clocks)
SKIP_START_SECONDS = 5


DETECTION_PROMPT = """You are the most thorough football film analyst in the world. The frames below are consecutive moments from a short window of game film, shown in time order.

Your job: identify every DISTINCT football play and extract the deepest possible structured data from what you can see. The consecutive frames often show ONE play developing (pre-snap → snap → result) — in that case return ONE play, using the pre-snap frame to read alignment and the later frames to confirm the result. If frames clearly span more than one snap, return one object per distinct snap.

Be thorough — catch every snap. A "play" is any snap: run, pass, screen, draw, QB sneak, punt, field goal, PAT, kickoff, or return.

Skip: timeouts, huddles, sideline/crowd shots, commercials, halftime, instant replays (same action shown again), pre-game, post-game, and frames with no live football action.

PHASE (side) — classify first:
- "offense": the team being scouted has the ball
- "defense": the team being scouted is on defense
- "special_teams": punt, kickoff, field goal, PAT, or any return

Each frame is labeled "Frame N (timestamp Ts)". For each play, pick the single best frame and report its number.

EXTRACT THE FOLLOWING — use null only if genuinely not determinable from the film:

CORE (every play):
- side: "offense", "defense", or "special_teams"
- frame: the Frame NUMBER shown above — REQUIRED
- down: 1–4 (null if not applicable)
- distance: yards to go as integer (null if not visible)
- field_position: "OWN 32" or "OPP 14" format (null if not visible)
- hash_position: "Left", "Right", or "Middle" — which hash the ball is on (read the ball position relative to field stripes)
- result: "Gain", "Loss", "Incomplete", "Touchdown", "Interception", "Fumble", "Sack", "Penalty", "First Down", "Made", "Missed", "Returned", "Touchback", or "Punt"
- yards_gained: integer (positive = gain, negative = loss), null if not determinable
- confidence: 0.0–1.0 — your confidence this is a real, unique play

OFFENSE (when side=offense):
- formation: "Shotgun", "I-Form", "Pistol", "Singleback", "Wildcat", "Empty", "Trips", "Bunch", "Spread", "Pro Set", or "Other"
- play_type: "Run", "Pass", "Screen", "Draw", "Option", "RPO", "Play Action", "QB Sneak", "Boot/Rollout", "Other"
- personnel: "10", "11", "12", "13", "20", "21", "22" (count RBs+TEs, e.g. 11=1RB 1TE 3WR) or null
- motion: true if any pre-snap offensive player is in motion, false otherwise
- run_direction: on run plays — "Inside Left", "Inside Right", "Outside Left", "Outside Right", "Up Middle"; null if not a run or can't tell
- run_concept: on run plays — "Zone", "Power/Gap", "Counter", "Trap", "Sweep/Toss", "Iso", "Draw", "Speed Option", "Other"; null if not a run
- pass_concept: on pass plays — "Quick Game", "Intermediate Routes", "Deep Shot", "Screen", "Play Action", "RPO", "Boot/Rollout", "Four Verts", "Mesh/Crossing", "Other"; null if not a pass
- pass_depth: on pass plays — "Behind LOS", "Short (1-5 yds)", "Intermediate (6-15 yds)", "Deep (16+ yds)"; null if incomplete/sack/can't tell

DEFENSE (when side=defense):
- defensive_front: "4-3", "3-4", "4-2-5", "3-3-5", "4-4", "5-2", "Nickel", "Dime", "Goal Line", or null
- coverage_shell: pre-snap safety alignment — "Two-High", "One-High", "Zero" (no deep safety); null if can't determine
- coverage: "Cover 0", "Cover 1", "Cover 2", "Cover 2 Man", "Cover 3", "Cover 4", "Cover 6", "Man", "Zone", or null
- blitz: "None", "Edge", "A-Gap", "Corner", "Safety", "Zone Blitz", "Interior", or null
- pressure_type: "4-Man Rush", "5-Man", "6-Man+", "Interior Pressure", "None"; null if can't tell

ALL PLAYS:
- play_description: ONE concise sentence describing what you see happening on the field — e.g. "QB takes shotgun snap, runs outside zone to the left for approximately 7 yards on first down" or "Defense shows two-high shell, drops to Cover 4 at snap, corner blitz off the edge forces an incomplete on a back-shoulder throw". This must be specific enough that a coach reviewing it could reconstruct the play without watching the film.

Return ONLY valid JSON in this exact format, nothing else:
{"plays": [{"side": "offense", "frame": 1, "down": null, "distance": null, "field_position": null, "hash_position": null, "result": null, "yards_gained": null, "confidence": 0.85, "formation": null, "play_type": null, "personnel": null, "motion": false, "run_direction": null, "run_concept": null, "pass_concept": null, "pass_depth": null, "defensive_front": null, "coverage_shell": null, "coverage": null, "blitz": null, "pressure_type": null, "play_description": null}]}

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
            video_path = os.path.join(LOCAL_STORAGE_DIR, game.r2_key.replace("/", os.sep))
            if not os.path.exists(video_path):
                raise ValueError(f"Local video file not found: {video_path}")
            video_source = video_path
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

                        # Replace prior auto-detected plays so a re-run doesn't duplicate
                        # (manually-tagged plays are preserved).
                        from sqlalchemy import delete as sa_delete
                        await db.execute(
                            sa_delete(Event).where(
                                Event.game_id == game_id,
                                Event.extra_data["auto_detected"].as_boolean() == True,
                            )
                        )

                        def _side(p):
                            s = (p.get("side") or "offense").lower().replace(" ", "_")
                            return s if s in ("offense", "defense", "special_teams") else "offense"

                        DEEP_FIELDS = (
                            "run_direction", "run_concept", "pass_concept", "pass_depth",
                            "coverage_shell", "pressure_type", "play_description",
                        )

                        events = [
                            Event(
                                game_id=game_id,
                                organization_id=org_id,
                                event_type="play",
                                side=_side(p),
                                time_seconds=p.get("time_seconds"),
                                down=p.get("down"),
                                distance=p.get("distance"),
                                field_position=p.get("field_position"),
                                hash_position=p.get("hash_position"),
                                formation=p.get("formation"),
                                play_type=p.get("play_type"),
                                defensive_front=p.get("defensive_front"),
                                coverage=p.get("coverage"),
                                blitz=p.get("blitz"),
                                result=p.get("result"),
                                yards_gained=p.get("yards_gained"),
                                personnel=p.get("personnel"),
                                motion=p.get("motion", False),
                                extra_data={
                                    "auto_detected": True,
                                    "confidence": p.get("confidence", 0.8),
                                    **{k: p[k] for k in DEEP_FIELDS if p.get(k) is not None},
                                },
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

    def _extract_frames(self, video_source: str, output_dir: str, duration_seconds: Optional[int]):
        """
        Extract frames at scene changes, capturing each frame's REAL timestamp
        (parsed from ffmpeg showinfo). Returns a list of (path, time_seconds)
        sorted by time. Falls back to fixed-interval frames if scenes are sparse.
        """
        scene_frames_dir = os.path.join(output_dir, "scene")
        os.makedirs(scene_frames_dir, exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(SKIP_START_SECONDS),
            "-i", video_source,
            "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
            "-vsync", "vfr",
            "-q:v", "3",
            "-f", "image2",
            os.path.join(scene_frames_dir, "frame_%06d.jpg"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        # showinfo logs one "pts_time:N" per emitted frame, in output order.
        pts_times = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", result.stderr or "")]
        scene_files = sorted(
            os.path.join(scene_frames_dir, f) for f in os.listdir(scene_frames_dir) if f.endswith(".jpg")
        )
        frames = []
        for i, f in enumerate(scene_files):
            # -ss before -i resets PTS to ~0, so add the skip offset back.
            t = (pts_times[i] if i < len(pts_times) else i * FALLBACK_INTERVAL) + SKIP_START_SECONDS
            frames.append((f, t))

        min_expected = max(10, (duration_seconds or 0) // 30)
        if len(frames) < min_expected:
            logger.info(f"[ai_detect] Only {len(frames)} scene frames — adding interval frames")
            interval_dir = os.path.join(output_dir, "interval")
            os.makedirs(interval_dir, exist_ok=True)
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(SKIP_START_SECONDS), "-i", video_source,
                "-vf", f"fps=1/{FALLBACK_INTERVAL}", "-q:v", "3",
                os.path.join(interval_dir, "frame_%06d.jpg"),
            ], capture_output=True, text=True, timeout=900)
            ifiles = sorted(
                os.path.join(interval_dir, f) for f in os.listdir(interval_dir) if f.endswith(".jpg")
            )
            for i, f in enumerate(ifiles):
                frames.append((f, SKIP_START_SECONDS + i * FALLBACK_INTERVAL))

        frames.sort(key=lambda x: x[1])

        # Cap total frames to control cost; sample evenly across the game.
        if len(frames) > MAX_FRAMES:
            step = len(frames) // MAX_FRAMES
            frames = frames[::step][:MAX_FRAMES]

        return frames

    async def _analyze_batch(self, batch, batch_idx: int, total_batches: int) -> list[dict]:
        """Send a batch of (path, time_seconds) frames to Claude Vision.

        The AI returns which FRAME each play is in; WE assign the real timestamp
        from that frame — never trusting an AI-estimated time.
        """
        import anthropic

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        content = []
        for i, (path, t) in enumerate(batch):
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            content.append({"type": "text", "text": f"Frame {i + 1} (timestamp {int(t)}s):"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})

        content.append({"type": "text", "text": DETECTION_PROMPT})

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        plays = parsed.get("plays", [])

        out = []
        tmin, tmax = batch[0][1], batch[-1][1]
        for p in plays:
            if p.get("confidence", 0) < 0.5:
                continue
            # Assign the REAL timestamp from the frame the AI picked.
            fr = p.get("frame")
            if isinstance(fr, (int, float)) and 1 <= int(fr) <= len(batch):
                p["time_seconds"] = round(batch[int(fr) - 1][1])
            else:
                # No valid frame ref — center it in this batch's real window.
                p["time_seconds"] = round(batch[len(batch) // 2][1])
            out.append(p)
        return out

    def _deduplicate_plays(self, plays: list[dict]) -> list[dict]:
        """Merge plays within 8s of each other (likely the same play seen across adjacent frames)."""
        if not plays:
            return []

        sorted_plays = sorted(plays, key=lambda p: p.get("time_seconds") or 0)
        deduped = [sorted_plays[0]]

        for play in sorted_plays[1:]:
            last_time = deduped[-1].get("time_seconds") or 0
            this_time = play.get("time_seconds") or 0
            if (this_time - last_time) < 8:
                # Keep the one with higher confidence
                if play.get("confidence", 0) > deduped[-1].get("confidence", 0):
                    deduped[-1] = play
            else:
                deduped.append(play)

        return deduped


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(AiDetectWorker().run_forever())
