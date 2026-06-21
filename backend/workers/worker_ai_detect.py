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


DETECTION_PROMPT = """You are the most thorough football film analyst in the world. Extract every possible piece of intelligence from each play. Coaches at every level depend on this data to win games.

FRAMES: Consecutive moments from game film shown in time order. One play often spans multiple frames (pre-snap → snap → result). Return ONE object per distinct snap. Use all frames to build the complete picture of each play.

SNAP EVERY PLAY. A play is any snap: run, pass, screen, draw, QB sneak, punt, field goal, PAT, kickoff, or return.

SKIP ONLY: timeouts, huddles, sideline/crowd shots, commercials, halftime, instant replays, pre/post-game, no live action.

PHASE — classify first:
- "offense": scouted team has the ball
- "defense": scouted team is on defense
- "special_teams": punt, kickoff, field goal, PAT, any return

Each frame is labeled "Frame N (timestamp Ts)". Report the best frame number for each play.

━━━ EXTRACT ALL FIELDS BELOW ━━━
Use null ONLY if genuinely not visible or determinable. Extract every field you can.

── CORE (every play) ──
- side: "offense" | "defense" | "special_teams"
- frame: Frame NUMBER — REQUIRED
- down: 1 | 2 | 3 | 4 | null
- distance: yards to go as integer | null
- field_position: "OWN 32" or "OPP 14" format | null
- hash_position: "Left" | "Right" | "Middle" — ball position on field | null
- score_situation: read scoreboard if visible — "Leading 8+" | "Leading 1-7" | "Tied" | "Trailing 1-7" | "Trailing 8+" | null
- tempo: pace of the offense — "No-Huddle" | "Hurry-Up" | "Normal" | "Clock Management" | null
- result: "Gain" | "Loss" | "Incomplete" | "Touchdown" | "Interception" | "Fumble" | "Sack" | "Penalty" | "First Down" | "Made" | "Missed" | "Returned" | "Touchback" | "Punt"
- yards_gained: integer (positive or negative) | null
- confidence: 0.0–1.0

── OFFENSE (side=offense) ──
- formation: "Shotgun" | "I-Form" | "Pistol" | "Singleback" | "Wildcat" | "Empty" | "Trips Left" | "Trips Right" | "Bunch" | "Spread" | "Pro Set" | "Other"
- receiver_alignment: how receivers are spread — "2x2" | "3x1" | "3x1 Trips" | "Empty" | "Bunch" | "Stack" | "Tight 2x2" | "Unbalanced" | null
- play_type: "Run" | "Pass" | "Screen" | "Draw" | "Option" | "RPO" | "Play Action" | "QB Sneak" | "Boot/Rollout" | "Other"
- personnel: "10" | "11" | "12" | "13" | "20" | "21" | "22" (RBs+TEs count, e.g. 11=1RB 1TE 3WR) | null
- motion: true if any player in pre-snap motion, false otherwise
- motion_type: if motion=true — "Jet Sweep Motion" | "H-Back Motion" | "WR Orbit" | "RB Flare" | "Trade/Swap" | "Fly Motion" | "Shift" | null
- run_direction: "Inside Left" | "Inside Right" | "Outside Left" | "Outside Right" | "Up Middle" | null
- run_gap: "A-Gap" | "B-Gap" | "C-Gap" | "Off-Tackle" | "Edge" | null
- run_concept: "Zone" | "Power/Gap" | "Counter" | "Trap" | "Sweep/Toss" | "Iso" | "Draw" | "Speed Option" | "Pin-Pull" | "Other" | null
- pass_concept: "Quick Game" | "Intermediate Routes" | "Deep Shot" | "Screen" | "Play Action" | "RPO" | "Boot/Rollout" | "Four Verts" | "Mesh/Crossing" | "Flood" | "Spot/Levels" | "Other" | null
- pass_depth: "Behind LOS" | "Short (1-5 yds)" | "Intermediate (6-15 yds)" | "Deep (16+ yds)" | null
- target_area: where the ball was thrown — "Left Flat" | "Right Flat" | "Left Sideline" | "Right Sideline" | "Middle Short" | "Middle Deep" | "Left Seam" | "Right Seam" | "Left Corner" | "Right Corner" | "Post" | "Go/Fly" | "Screen Left" | "Screen Right" | null

── DEFENSE (side=defense) ──
- defensive_front: "4-3" | "3-4" | "4-2-5" | "3-3-5" | "4-4" | "5-2" | "Nickel" | "Dime" | "Goal Line" | null
- linebacker_alignment: "Walk-Up" | "Normal Stack" | "Dropped" | "Wide (Overhang)" | null
- coverage_shell: pre-snap safety look — "Two-High" | "One-High" | "Zero" | null
- safety_rotation: what safeties actually do post-snap — "Stayed Two-High" | "Rotated Single High" | "Rolled Left" | "Rolled Right" | "Robber/Rat" | "Pressed Up" | null
- coverage: "Cover 0" | "Cover 1" | "Cover 2" | "Cover 2 Man" | "Cover 3" | "Cover 4" | "Cover 6" | "Man" | "Zone" | null
- corner_technique: "Press" | "Off/Cushion" | "Bail/Zone Turn" | null
- blitz: "None" | "Edge" | "A-Gap" | "Corner" | "Safety" | "Zone Blitz" | "Interior" | null
- pressure_gap: WHERE the pressure/blitz actually came from — "Edge Left" | "Edge Right" | "A-Gap Left" | "A-Gap Right" | "B-Gap" | "Interior" | null
- pressure_type: "4-Man Rush" | "5-Man" | "6-Man+" | "Interior Pressure" | "None" | null

── EVERY PLAY ──
- play_description: ONE sharp sentence describing exactly what you see — formation, concept, result. Specific enough that a coach can reconstruct the play without the film. Examples: "Trips Right Shotgun 11 personnel, counter run to B-gap right, linebacker fills wrong arm, 8-yard gain to the field." | "Defense shows two-high shell, safety rotates single post-snap to Cover 1, corner bail outside, slant route hits soft spot in coverage for 12 yards."

━━━ JSON FORMAT ━━━
Return ONLY this JSON, nothing else:
{"plays": [{"side": "offense", "frame": 1, "down": null, "distance": null, "field_position": null, "hash_position": null, "score_situation": null, "tempo": null, "result": null, "yards_gained": null, "confidence": 0.85, "formation": null, "receiver_alignment": null, "play_type": null, "personnel": null, "motion": false, "motion_type": null, "run_direction": null, "run_gap": null, "run_concept": null, "pass_concept": null, "pass_depth": null, "target_area": null, "defensive_front": null, "linebacker_alignment": null, "coverage_shell": null, "safety_rotation": null, "coverage": null, "corner_technique": null, "blitz": null, "pressure_gap": null, "pressure_type": null, "play_description": null}]}

Zero plays in these frames: {"plays": []}"""


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
                            # Round 1
                            "run_direction", "run_concept", "pass_concept", "pass_depth",
                            "coverage_shell", "pressure_type", "play_description",
                            # Round 2 — deeper extraction
                            "run_gap", "target_area", "motion_type", "receiver_alignment",
                            "corner_technique", "safety_rotation", "pressure_gap",
                            "linebacker_alignment", "tempo", "score_situation",
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
