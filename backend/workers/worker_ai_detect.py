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


DETECTION_PROMPT = """You are the most thorough football film analyst in the world. The frames below are consecutive moments from game film (a few seconds apart), shown in time order.

Your job: identify every DISTINCT football play in this window and extract MAXIMUM structured intelligence. Consecutive frames often show ONE play developing (pre-snap → snap → result) — return ONE play using pre-snap frames for formation/alignment and post-snap frames for result. If frames clearly span multiple snaps, return one object per snap.

Catch EVERY snap: run, pass, screen, draw, QB sneak, RPO, option, punt, field goal, PAT, kickoff, return.

Skip: timeouts, huddles, sideline shots, commercials, halftime, replays (same action shown twice), pre-game, post-game, no live action.

PHASE classification (side field):
- "offense": scouted team has the ball
- "defense": scouted team is defending
- "special_teams": punt, kickoff, field goal, PAT, any return

EXTRACT ALL FIELDS BELOW. Use null only if truly unreadable from film. Make your best coaching-level read.

CORE (from scoreboard + field):
- side: "offense", "defense", or "special_teams"
- frame: Frame NUMBER where play best seen (REQUIRED)
- down: 1-4 or null
- distance: yards to go or null
- field_position: "OWN 32", "OPP 14", etc. or null
- formation: "Shotgun", "I-Form", "Pistol", "Singleback", "Wildcat", "Empty", "Trips", "Bunch", "Pro Set", "Ace", "Offset I", "Other"
- play_type: offense → "Run", "Pass", "Screen", "Draw", "Option", "RPO", "QB Sneak", "Other"; special_teams → "Punt", "Kickoff", "Field Goal", "PAT", "Punt Return", "Kick Return", "Onside Kick", "Fake"
- personnel: "10", "11", "12", "13", "20", "21", "22", "23", or null
- result: "Gain", "Loss", "Incomplete", "Touchdown", "Interception", "Fumble", "Sack", "Penalty", "First Down", "Made", "Missed", "Returned", "Touchback", "Punt"
- yards_gained: integer or null
- confidence: 0.0-1.0

OFFENSE DEEP EXTRACTION:
- hash_position: "Left Hash", "Middle", "Right Hash" or null
- motion: true/false (any pre-snap offensive motion)
- motion_type: "Jet Sweep", "Orbit", "H-Back Shift", "WR Crack", "RB Flare", "TE Arc", "Stack Release", "Fly Motion", null — read from pre-snap movement pattern
- receiver_alignment: "2x2", "3x1", "3x2", "2x1", "Bunch Left", "Bunch Right", "Stack", "Compressed", null
- run_direction: "Left", "Right", "Middle", null — only if play_type=Run
- run_gap: "A", "B", "C", "D", "Edge" — which gap the ball carrier attacked (null if not run)
- run_concept: "Inside Zone", "Outside Zone", "Power", "Counter", "Trap", "Sweep", "Toss", "Draw", "Option Keep", "QB Sneak", null
- pass_concept: "Levels", "Mesh", "Flood", "Y-Cross", "4-Verts", "Smash", "Sail", "Hi-Lo", "Stick", "Spacing", "Dagger", "Wheel", "Drive", "Slot Fade", "Seam", "Deep Cross", "Post/Corner", "Drive", null
- pass_depth: "Screen/Behind LOS", "Short (1-5)", "Intermediate (6-14)", "Deep (15+)" — target depth behind LOS, null if not pass
- target_area: "Left Flat", "Right Flat", "Left Sideline", "Right Sideline", "Left Slot", "Right Slot", "Middle Short", "Middle Deep", "Seam Left", "Seam Right", "Backfield", null
- tempo: "Hurry Up", "No Huddle", "Normal", "Slow/Deliberate" — pace of the offense getting to the line
- score_situation: "Leading 8+", "Leading 1-7", "Tied", "Trailing 1-7", "Trailing 8+" — infer from scoreboard if visible
- play_description: 1-2 sentence coaching description of exactly what happened (e.g. "Power right to the B-gap, RB cuts back to A for 6 yards. Lead block sealed the WILL.")

DEFENSE DEEP EXTRACTION:
- defensive_front: "4-3", "3-4", "4-2-5", "3-3-5", "4-4", "5-2", "Nickel", "Dime", "Goal Line", "Bear", "Okie", null
- coverage: "Cover 0", "Cover 1", "Cover 2", "Cover 2 Man", "Cover 3", "Cover 4", "Cover 6", "Man", "Zone", "Tampa 2", null
- coverage_shell: "2-High", "1-High", "0-High" — pre-snap safety alignment
- safety_rotation: "Rotated Left", "Rotated Right", "Stayed 2-High", "Rolled Down", "Robber", null — post-snap safety movement
- corner_technique: "Press", "Off Coverage", "Trail", "Bail", "Squat", null
- blitz: "None", "Edge", "A-Gap", "B-Gap", "Corner", "Safety", "Zone Blitz", "Fire Zone", "Double A-Gap"
- pressure_type: "Base Rush", "Overload Left", "Overload Right", "Interior Push", "Twist", "Stunt", "Zero Blitz", null
- pressure_gap: "A", "B", "C", "Edge" — where primary pressure came from
- linebacker_alignment: "Under", "Over", "Tite", "Stack", "Spread", null

Return ONLY valid JSON, nothing else:
{"plays": [{"side": "offense", "frame": 1, "down": null, "distance": null, "field_position": null, "formation": null, "play_type": null, "personnel": null, "result": null, "yards_gained": null, "confidence": 0.8, "hash_position": null, "motion": false, "motion_type": null, "receiver_alignment": null, "run_direction": null, "run_gap": null, "run_concept": null, "pass_concept": null, "pass_depth": null, "target_area": null, "tempo": null, "score_situation": null, "play_description": null, "defensive_front": null, "coverage": null, "coverage_shell": null, "safety_rotation": null, "corner_technique": null, "blitz": null, "pressure_type": null, "pressure_gap": null, "linebacker_alignment": null}]}

If zero plays: {"plays": []}"""


DETECTION_PROMPT_BASKETBALL = """You are the most thorough basketball film analyst in the world. Extract every possible piece of intelligence from each possession or event. Coaches depend on this data to build game plans.

FRAMES: Consecutive moments from basketball game film. Each frame cluster typically covers one possession or key event.

CAPTURE EVERY EVENT: shots (made or missed), turnovers, fouls, rebounds (offensive/defensive), assists, steals, blocks, timeouts, and significant possessions.

SKIP: dead balls between possessions already captured, halftime, non-game footage.

PHASE — classify first:
- "offense": scouted team has the ball
- "defense": scouted team is defending
- "transition": fast break (either direction)

Each frame is labeled "Frame N (timestamp Ts)". Report the best frame number.

━━━ EXTRACT ALL FIELDS BELOW ━━━
Use null ONLY if genuinely not determinable.

── CORE (every event) ──
- side: "offense" | "defense" | "transition"
- frame: Frame NUMBER — REQUIRED
- event_type: "shot" | "turnover" | "foul" | "rebound" | "assist" | "steal" | "block" | "timeout" | "possession"
- result: "Made" | "Missed" | "Blocked" | "And-1" | "Fouled" | "Stolen" | "Out of Bounds" | "Offensive Foul" | "Good" | null
- score_margin: from scoreboard if visible — "Up 10+" | "Up 1-9" | "Tied" | "Down 1-9" | "Down 10+" | null
- quarter: 1 | 2 | 3 | 4 | 5 (OT) | null
- shot_clock_range: "Early (>15s)" | "Mid (8-14s)" | "Late (<7s)" | "Buzzer" | null
- confidence: 0.0–1.0

── OFFENSE (side=offense or transition) ──
- play_action: primary offensive action — "Pick and Roll" | "Pick and Pop" | "Isolation" | "Post Up" | "Drive and Kick" | "DHO (Dribble Handoff)" | "Off-Ball Screen" | "Catch and Shoot" | "Transition Layup" | "Putback" | "BLOB" | "SLOB" | "Horns" | "Elbow Set" | "Curl" | "Backdoor Cut" | "Lob" | "Other" | null
- shot_zone: where the shot came from — "Restricted Area" | "Paint Non-RA" | "Left Corner 3" | "Right Corner 3" | "Left Wing 3" | "Right Wing 3" | "Top of Key 3" | "Left Elbow Mid" | "Right Elbow Mid" | "Left Mid-Range" | "Right Mid-Range" | "Mid-Range Center" | "Half Court" | null
- shot_type: "Layup" | "Dunk" | "Floater" | "Pull-Up Jumper" | "Catch and Shoot" | "Step-Back" | "Post Fade" | "Hook Shot" | "Tip-In" | "Bank Shot" | "3-Pointer" | null
- shot_distance_ft: estimated feet from basket as integer | null
- screen_type: "Ball Screen" | "Off-Ball Screen" | "Double Screen" | "Flare Screen" | "Back Screen" | "Cross Screen" | "Stagger" | null
- ball_screen_position: "Top" | "Wing Left" | "Wing Right" | "Elbow" | "Drag" | null
- transition_type: "Primary Break" | "Secondary Break" | "Early Offense" | null
- paint_touch: true if ball entered paint on this possession, false otherwise
- kick_out: true if ball was driven into paint then kicked out to perimeter, false otherwise
- assist_type: "Drive and Kick" | "Post Kick" | "Skip Pass" | "Hand-Off" | "Corner Kick" | "Swing" | null
- motion: true if team running motion offense (constant movement, no set play), false otherwise

── INBOUND PLAYS — extract these whenever play_action is BLOB or SLOB ──
These fields are CRITICAL for coaching — extract as precisely as possible from the film.
- inbound_type: "BLOB" (baseline out of bounds) | "SLOB" (sideline out of bounds) | null
- inbound_side: where the ball is being inbounded from (read the lines/player position on court):
  BLOB → "Left Baseline" | "Right Baseline" | "Under Basket"
  SLOB → "Left Sideline" | "Right Sideline" | "Half Court" | "Frontcourt Left" | "Frontcourt Right"
- inbound_set: formation/alignment the offense sets up before the inbound —
  "Stack" (players lined up vertically near lane) | "Box" (4 players at each block/elbow) | "Line" (players spread along lane) |
  "Diamond" (players at 4 points around key) | "Horns" (two players at elbows, one at top, one under) |
  "Spread" (players spaced wide) | "1-4 High" (one player at block, four across foul line extended) | null
- inbound_primary_action: the designed play off the inbound —
  "Back Screen" | "Flare Screen" | "Cross Screen" | "Rub Cut" | "Lob Over Top" | "Post Seal" |
  "Pin Down" | "Curl Cut" | "Straight Cut" | "Quick Hitter Direct" | "Double Screen" |
  "Stagger Screen" | "Fake Reverse" | "Step-In" | null
- inbound_scorer_position: where the designed scorer ends up when they catch — same values as shot_zone
- inbound_defense_coverage: how the DEFENSE handles this inbound play —
  "Man Switch" | "Man No Switch" | "Zone" | "Box and 1" | "Deny Inbounder" |
  "Full Denial All" | "ICE Baseline" | "Blitz Cutter" | null
- inbound_situation: what game situation triggered this inbound —
  "End of Quarter" | "End of Game (<30s)" | "After Score Normal" | "After Timeout" |
  "Foul Situation" | "Normal Halfcourt" | null
- inbound_result_zone: where the actual shot or scoring attempt ended up — same values as shot_zone | null

── DEFENSE (side=defense) ──
- defensive_scheme: "Man" | "Zone 2-3" | "Zone 3-2" | "Zone 1-3-1" | "Match-Up Zone" | "Full Court Press Man" | "Full Court Press Zone" | "Half Court Trap" | null
- hedge_style: how they cover ball screens — "Hard Hedge" | "Drop Coverage" | "Switch" | "ICE/Push" | "Blitz/Double" | "Hedge and Recover" | null
- help_defense: "Collapsing" | "Weak Side Help" | "No Help" | "Sagging" | null
- deny_style: "Full Denial" | "Open/Sag" | "Body-Up" | null
- press_trigger: if pressing — "Made Basket" | "Turnover" | "Always" | null
- oob_defense_coverage: when defending opponent BLOB/SLOB, what coverage do they use —
  "Man Switch" | "Man No Switch" | "Zone" | "Box and 1" | "Deny Inbounder" | "Full Denial All" | null
  (use this when side=defense and the opponent is running an inbound play)

── EVERY EVENT ──
- play_description: ONE sharp sentence describing the possession/action. Specific enough to reconstruct without film. For inbounds: name the set, the action, and what happened. Examples: "BLOB right baseline: Box set, back screen frees cutter at restricted area, lob over zone for layup (made)." | "SLOB left sideline after timeout: Stack set, cross screen action, shooter pops to left wing 3 (missed, long)." | "PG drives baseline, draws hard hedge from center on ball screen at elbow, kicks to corner shooter for open 3 (missed)."

━━━ JSON FORMAT ━━━
Return ONLY this JSON:
{"plays": [{"side": "offense", "frame": 1, "event_type": "shot", "result": null, "score_margin": null, "quarter": null, "shot_clock_range": null, "confidence": 0.85, "play_action": null, "shot_zone": null, "shot_type": null, "shot_distance_ft": null, "screen_type": null, "ball_screen_position": null, "transition_type": null, "paint_touch": false, "kick_out": false, "assist_type": null, "motion": false, "inbound_type": null, "inbound_side": null, "inbound_set": null, "inbound_primary_action": null, "inbound_scorer_position": null, "inbound_defense_coverage": null, "inbound_situation": null, "inbound_result_zone": null, "defensive_scheme": null, "hedge_style": null, "help_defense": null, "deny_style": null, "press_trigger": null, "oob_defense_coverage": null, "play_description": null}]}

Zero events: {"plays": []}"""


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
            sport = (game.sport or "football").lower()

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
                        plays = await self._analyze_batch(batch, batch_idx, len(batches), sport)
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
                            valid = ("offense", "defense", "special_teams", "transition")
                            return s if s in valid else "offense"

                        DEEP_FIELDS = (
                            # Football round 1
                            "run_direction", "run_concept", "pass_concept", "pass_depth",
                            "coverage_shell", "pressure_type", "play_description",
                            # Football round 2
                            "run_gap", "target_area", "motion_type", "receiver_alignment",
                            "corner_technique", "safety_rotation", "pressure_gap",
                            "linebacker_alignment", "tempo", "score_situation",
                            # Basketball
                            "play_action", "shot_zone", "shot_type", "shot_distance_ft",
                            "screen_type", "ball_screen_position", "transition_type",
                            "paint_touch", "kick_out", "assist_type",
                            "defensive_scheme", "hedge_style", "help_defense", "deny_style", "press_trigger",
                            "score_margin", "quarter", "shot_clock_range",
                            # Basketball inbound plays
                            "inbound_type", "inbound_side", "inbound_set", "inbound_primary_action",
                            "inbound_scorer_position", "inbound_defense_coverage",
                            "inbound_situation", "inbound_result_zone",
                            "oob_defense_coverage",
                        )

                        events = [
                            Event(
                                game_id=game_id,
                                organization_id=org_id,
                                event_type=p.get("event_type", "shot") if sport == "basketball" else "play",
                                side=_side(p),
                                time_seconds=p.get("time_seconds"),
                                down=p.get("down"),
                                distance=p.get("distance"),
                                field_position=p.get("field_position"),
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

    async def _analyze_batch(self, batch, batch_idx: int, total_batches: int, sport: str = "football") -> list[dict]:
        """Send a batch of (path, time_seconds) frames to Claude Vision.

        The AI returns which FRAME each play is in; WE assign the real timestamp
        from that frame — never trusting an AI-estimated time.
        """
        import anthropic

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = DETECTION_PROMPT_BASKETBALL if sport == "basketball" else DETECTION_PROMPT

        content = []
        for i, (path, t) in enumerate(batch):
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            content.append({"type": "text", "text": f"Frame {i + 1} (timestamp {int(t)}s):"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})

        content.append({"type": "text", "text": prompt})

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
