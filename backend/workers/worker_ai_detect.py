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
from backend.services.agent_log import (
    log_agent_action, confidence_band,
    AGENT_NAME, AGENT_ROLE, HARD_FLOOR, ESCALATION_THRESHOLD,
)
from backend.workers.base import BaseWorker

logger = logging.getLogger(__name__)

# Cap on total frames analyzed per game (recall vs cost). ~MAX_FRAMES/5 Claude calls.
MAX_FRAMES = 2700          # was 900 — 3x increase for recall (~1 frame/1.33s over 60min)
# Max frames to send Claude per batch (controls token cost)
FRAMES_PER_BATCH = 5       # unchanged — keep Claude batch size
# Minimum scene-change threshold (0–1). Lower = more sensitive (catches more snaps).
SCENE_THRESHOLD = 0.18     # was 0.27 — more sensitive snap detection
# Seconds between fixed-interval frame samples (tighter = catch more plays)
FALLBACK_INTERVAL = 2.0    # was 5.0 — tighter coverage, no >2s gap
# Confidence gate — plays below this are dropped
MIN_CONFIDENCE = 0.5       # unchanged — keep quality gate
# Drop frames closer together than this (dedup same-moment frames)
CLUSTER_GAP_SECONDS = 1.5  # new — snap-aware frame clustering
# Skip the first N seconds (avoids intro graphics / countdown clocks)
SKIP_START_SECONDS = 5
# Bumped on each detection-pipeline change so the DB agent log proves which code ran.
CODE_VERSION = "recall-v3-diag"


DETECTION_PROMPT = """You are the most thorough football film analyst in the world. The frames below are consecutive moments from game film (a few seconds apart), shown in time order.

Your job: identify every DISTINCT football play in this window and extract MAXIMUM structured intelligence. Consecutive frames often show ONE play developing (pre-snap → snap → result) — return ONE play using pre-snap frames for formation/alignment and post-snap frames for result. If frames clearly span multiple snaps, return one object per snap.

Catch EVERY snap: run, pass, screen, draw, QB sneak, RPO, option, punt, field goal, PAT, kickoff, return.

Skip: timeouts, huddles, sideline shots, commercials, halftime, replays (same action shown twice), pre-game, post-game, no live action.

IMAGE SET PER FRAME: For each frame you receive the full image PLUS two zoomed crops — the "lower" and "upper" score/overlay zones (magnified 2x). The broadcast score graphic (the "score bug") almost always shows DOWN, DISTANCE, SCORE, QUARTER, and GAME CLOCK. READ THESE DIGITS CAREFULLY FROM THE ZOOMED CROPS — they are your source of truth for down/distance/score/clock. Down & distance usually appears like "2ND & 7" or "3RD & GOAL". If the graphic is genuinely absent (coaches' end-zone film with no overlay), set those fields to null and note it in blind_spot — do NOT guess.

RUN vs PASS — decide from the SEQUENCE across the consecutive frames, never a single still: QB hands the ball to a back or keeps it and runs = "Run"; QB drops straight back, the ball is in the air, or a receiver is catching downfield = "Pass"; quick flip behind the line = "Screen". If you cannot tell, use null rather than guessing.

FRAME PHASE — first judge what moment each frame shows, then read accordingly:
- pre_snap: offense set in formation at the line → best for formation, personnel, down, distance, field_position
- at_snap: the snap / handoff / drop → best for run vs pass, play_type
- post_play: the tackle / catch / end of play → best for result and yardage cues
- between_plays / unclear: huddle, walk-up, sideline, replay, crowd → NOT a live snap; do not emit a play for these
Read down/distance/formation from pre_snap frames, run-vs-pass from at_snap frames, and result from post_play frames. Do not try to read formation or down off a mid-action or between-plays frame.

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
- confidence: 0.0-1.0 — your confidence in THIS play's read overall
- blind_spot: SINGLE-CAMERA HONESTY. If the fixed camera angle prevented a confident read of something important, name it in a short phrase. Examples: "Backside blocking off-screen", "Coverage rotation behind LOS not visible", "Ball carrier obscured by line at handoff", "Down/distance not on scoreboard this frame", "Far hash action cut off by frame edge". Use null ONLY if the entire play was clearly visible. NEVER invent data for anything off-camera — flag it here instead.

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
- is_play_action: true if there was a handoff fake before a pass attempt, false otherwise (only meaningful when play_type=Pass)
- screen_subtype: if this is a screen pass — "RB Screen" | "WR Screen" | "TE Screen" | "Bubble Screen" | "Slip Screen" | "Tunnel Screen" | null
- goal_line: true if the offense is inside the opponent's 5-yard line, false otherwise

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

PLAYER IDENTIFICATION (single-camera, best-effort — NEVER guess a number):
- players: array of the key players whose JERSEY NUMBER you can actually READ on this play. Only include a player if the number is legible — if you cannot read it, leave them out. Each entry: {"jersey": "<number as string>", "team": "offense" or "defense", "role": "<role>", "confidence": 0.0-1.0}. Football roles: "passer", "ball_carrier", "rusher", "targeted_receiver", "receiver", "tackler", "pass_rusher", "interceptor", "kicker", "returner", "blocker". Use [] if no jersey is legible.
- primary_player_jersey: the jersey number (string) of the MAIN actor of the play (ball carrier, passer, or kicker), or null if not legible.

Return ONLY valid JSON, nothing else:
{"plays": [{"side": "offense", "frame": 1, "down": null, "distance": null, "field_position": null, "formation": null, "play_type": null, "personnel": null, "result": null, "yards_gained": null, "confidence": 0.8, "blind_spot": null, "hash_position": null, "motion": false, "motion_type": null, "receiver_alignment": null, "run_direction": null, "run_gap": null, "run_concept": null, "pass_concept": null, "pass_depth": null, "target_area": null, "tempo": null, "score_situation": null, "play_description": null, "is_play_action": false, "screen_subtype": null, "goal_line": false, "defensive_front": null, "coverage": null, "coverage_shell": null, "safety_rotation": null, "corner_technique": null, "blitz": null, "pressure_type": null, "pressure_gap": null, "linebacker_alignment": null, "players": [], "primary_player_jersey": null}]}

If zero plays: {"plays": []}"""


DETECTION_PROMPT_BASKETBALL = """You are the most thorough basketball film analyst in the world. Extract every possible piece of intelligence from each possession or event. Coaches depend on this data to build game plans.

FRAMES: Consecutive moments from basketball game film. Each frame cluster typically covers one possession or key event.

CAPTURE EVERY EVENT: shots (made or missed), turnovers, fouls, rebounds (offensive/defensive), assists, steals, blocks, timeouts, and significant possessions.

SKIP: dead balls between possessions already captured, halftime, non-game footage.

IMAGE SET PER FRAME: For each frame you receive the full image PLUS two zoomed crops — the "lower" and "upper" score/overlay zones (magnified 2x). The broadcast score graphic usually shows SCORE, QUARTER, and GAME/SHOT CLOCK. Read those digits from the zoomed crops; use them as the source of truth for score_margin, quarter, and shot_clock_range. If no graphic is present, set them null and note it in blind_spot — do not guess.

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
- confidence: 0.0–1.0 — your confidence in THIS possession's read overall
- blind_spot: SINGLE-CAMERA HONESTY. If the fixed camera angle prevented a confident read, name it in a short phrase. Examples: "Weak-side action off-screen", "Shot clock not visible this frame", "Ball handler obscured in traffic", "Defender assignment unclear from this angle", "Play developed below the baseline camera cutoff". Use null ONLY if the entire possession was clearly visible. NEVER invent off-camera data — flag it here instead.

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
- vs_zone: true if this possession is against a zone defense, false if vs man
- zone_offense_action: if vs_zone=true, what offensive action — "Skip Pass" | "High Post Entry" | "Flash Cut" | "Baseline Runner" | "Corner Flash" | "Swing Pass" | "Dribble Entry" | null
- press_break_action: if defending team applied a press, how was it broken — "Push Center" | "Outlet Wing" | "Long Pass" | "Dribble Up" | "Stack Break" | null
- clutch_situation: true if score margin is within 5 points AND in Q4 or OT, false otherwise
- foul_drawn_action: if a foul was drawn, what action caused it — "Drive" | "Post Move" | "Pump Fake" | "Catch and Shoot" | "Screen Set" | "And-1 Drive" | null

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

── PLAYER IDENTIFICATION (single-camera, best-effort — NEVER guess a number) ──
- players: array of players whose JERSEY NUMBER you can actually READ on this event. Only include legible numbers — never guess. Each: {"jersey": "<number as string>", "team": "offense" or "defense", "role": "<role>", "confidence": 0.0-1.0}. Basketball roles: "shooter", "ball_handler", "passer", "screener", "roll_man", "cutter", "defender", "rebounder", "fouler", "fouled", "assister", "stealer", "blocker". Use [] if no jersey is legible.
- primary_player_jersey: jersey number (string) of the MAIN actor (shooter / ball handler), or null if not legible.

── EVERY EVENT ──
- play_description: ONE sharp sentence describing the possession/action. Specific enough to reconstruct without film. For inbounds: name the set, the action, and what happened. Examples: "BLOB right baseline: Box set, back screen frees cutter at restricted area, lob over zone for layup (made)." | "SLOB left sideline after timeout: Stack set, cross screen action, shooter pops to left wing 3 (missed, long)." | "PG drives baseline, draws hard hedge from center on ball screen at elbow, kicks to corner shooter for open 3 (missed)."

━━━ JSON FORMAT ━━━
Return ONLY this JSON:
{"plays": [{"side": "offense", "frame": 1, "event_type": "shot", "result": null, "score_margin": null, "quarter": null, "shot_clock_range": null, "confidence": 0.85, "blind_spot": null, "play_action": null, "shot_zone": null, "shot_type": null, "shot_distance_ft": null, "screen_type": null, "ball_screen_position": null, "transition_type": null, "paint_touch": false, "kick_out": false, "assist_type": null, "motion": false, "vs_zone": false, "zone_offense_action": null, "press_break_action": null, "clutch_situation": false, "foul_drawn_action": null, "inbound_type": null, "inbound_side": null, "inbound_set": null, "inbound_primary_action": null, "inbound_scorer_position": null, "inbound_defense_coverage": null, "inbound_situation": null, "inbound_result_zone": null, "defensive_scheme": null, "hedge_style": null, "help_defense": null, "deny_style": null, "press_trigger": null, "oob_defense_coverage": null, "players": [], "primary_player_jersey": null, "play_description": null}]}

Zero events: {"plays": []}"""


class AiDetectWorker(BaseWorker):
    job_type = "ai_detect"

    async def handle(self, payload: dict) -> dict:
        game_id = payload["game_id"]
        dry_run = bool(payload.get("dry_run"))
        job_id = payload.get("_job_id")
        return await self._detect_plays(game_id, dry_run=dry_run, job_id=job_id)

    async def _detect_plays(self, game_id: str, dry_run: bool = False, job_id=None) -> dict:
        # ── Load game ──────────────────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            if game.status != "ready":
                raise ValueError(f"Game not ready for detection (status={game.status})")
            sport = (game.sport or "football").lower()
            org_id = game.organization_id

        # UATP identity disclosure — the agent says who it is and what it will do
        # BEFORE it acts, every run.
        await log_agent_action(
            game_id=game_id, organization_id=str(org_id), job_id=job_id,
            phase="init", level="info",
            action=f"{AGENT_NAME} starting film analysis",
            reason=(
                f"I am {AGENT_NAME} ({AGENT_ROLE}). I will scan this {sport} film frame by "
                f"frame, identify every play, and record each with a confidence score. "
                + ("DRY RUN: I will simulate detection without saving any plays."
                   if dry_run else "Confident reads are saved; low-confidence reads are flagged for your review, never presented as fact.")
            ),
            detail={"sport": sport, "dry_run": dry_run},
        )

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
                # Snap-aware clustering: drop same-moment duplicates so each batch
                # covers distinct play opportunities rather than near-identical frames.
                frame_paths = self._cluster_frames(frame_paths, CLUSTER_GAP_SECONDS)

                if not frame_paths:
                    logger.warning(f"[ai_detect] No frames extracted for game {game_id}")
                    await log_agent_action(
                        game_id=game_id, organization_id=str(org_id), job_id=job_id,
                        phase="frame_extraction", level="error",
                        action="No frames could be extracted",
                        reason="ffmpeg returned zero frames from this film. The file may be unreadable, "
                               "empty, or in an unsupported format. Detection cannot proceed.",
                    )
                    async with AsyncSessionLocal() as db:
                        await db.execute(update(Game).where(Game.id == game_id).values(status="ready"))
                        await db.commit()
                    return {"game_id": game_id, "plays_detected": 0}

                logger.info(f"[ai_detect] Extracted {len(frame_paths)} frames for game {game_id}")
                await log_agent_action(
                    game_id=game_id, organization_id=str(org_id), job_id=job_id,
                    phase="frame_extraction", level="info",
                    action=f"Extracted {len(frame_paths)} frames to analyze",
                    reason="Sampled the film at scene changes plus a uniform interval grid to catch every "
                           "snap. Each frame carries its real timestamp.",
                    detail={"frame_count": len(frame_paths), "after_cluster": len(frame_paths),
                            **getattr(self, "_extract_diag", {})},
                )

                # ── Send batches to Claude Vision ──────────────────────────
                all_plays = []
                batches = [frame_paths[i:i + FRAMES_PER_BATCH] for i in range(0, len(frame_paths), FRAMES_PER_BATCH)]

                # Log a heartbeat roughly every 10% of batches so the live panel
                # shows steady progress without flooding the log.
                log_every = max(1, len(batches) // 10)
                failed_batches = 0
                for batch_idx, batch in enumerate(batches):
                    try:
                        plays = await self._analyze_batch(batch, batch_idx, len(batches), sport)
                        all_plays.extend(plays)
                        logger.info(f"[ai_detect] Batch {batch_idx+1}/{len(batches)}: {len(plays)} plays")
                        if plays and (batch_idx % log_every == 0 or batch_idx == len(batches) - 1):
                            confs = [p.get("confidence", 0) for p in plays]
                            avg_c = round(sum(confs) / len(confs), 2) if confs else None
                            await log_agent_action(
                                game_id=game_id, organization_id=str(org_id), job_id=job_id,
                                phase="vision_analysis", level="info",
                                action=f"Analyzed segment {batch_idx+1} of {len(batches)} — {len(plays)} play(s) read",
                                reason=f"Reading play development across consecutive frames. "
                                       f"Segment confidence: {confidence_band(avg_c)}.",
                                confidence=avg_c,
                                detail={"batch": batch_idx + 1, "total_batches": len(batches),
                                        "plays_in_batch": len(plays)},
                            )
                    except Exception as e:
                        failed_batches += 1
                        logger.warning(f"[ai_detect] Batch {batch_idx+1} failed: {e}")
                        await log_agent_action(
                            game_id=game_id, organization_id=str(org_id), job_id=job_id,
                            phase="vision_analysis", level="warn",
                            action=f"Segment {batch_idx+1} could not be read",
                            reason=f"This segment failed and was skipped so the rest of the film still gets "
                                   f"analyzed. Cause: {str(e)[:200]}",
                            detail={"batch": batch_idx + 1},
                        )
                        continue

                # ── Deduplicate by time (within 5s = same play) ───────────
                deduped = self._deduplicate_plays(all_plays)
                # Derive yards/result from the down-and-distance progression — far more
                # reliable than reading yardage off a still frame.
                if sport in ("football", "flag_football"):
                    deduped = self._derive_from_sequence(deduped)
                    deduped = self._derive_field_position(deduped)
                logger.info(f"[ai_detect] {len(all_plays)} raw → {len(deduped)} after dedup")

                # ── Confidence + escalation accounting (UATP) ──────────────
                all_confs = [p.get("confidence", 0.8) for p in deduped]
                avg_conf = round(sum(all_confs) / len(all_confs), 2) if all_confs else None
                # Gray-band plays (kept but below the confident threshold) are flagged
                # for human review — the agent never presents them as fact.
                needs_review_count = sum(
                    1 for p in deduped if p.get("confidence", 0.8) < ESCALATION_THRESHOLD
                )

                # ── DRY RUN: simulate, never write (UATP staging mode) ─────
                if dry_run:
                    await log_agent_action(
                        game_id=game_id, organization_id=str(org_id), job_id=job_id,
                        phase="dry_run", level="success",
                        action=f"DRY RUN complete — would have saved {len(deduped)} play(s)",
                        reason=f"Simulation only. No plays were written. {needs_review_count} would be "
                               f"flagged for review. Overall confidence: {confidence_band(avg_conf)}.",
                        confidence=avg_conf,
                        detail={"would_persist": len(deduped), "would_flag_for_review": needs_review_count,
                                "failed_batches": failed_batches},
                    )
                    return {"game_id": game_id, "plays_detected": 0, "dry_run": True,
                            "would_persist": len(deduped)}

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
                            # Basketball zone/press/clutch/foul
                            "vs_zone", "zone_offense_action", "press_break_action",
                            "clutch_situation", "foul_drawn_action",
                            # Football moat fields
                            "is_play_action", "screen_subtype", "goal_line",
                            # Single-camera transparency (all sports)
                            "blind_spot",
                            # Player-level tracking (all sports)
                            "players", "primary_player_jersey",
                            # Derivation provenance
                            "yards_source", "field_position_derived",
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
                                    # UATP human-escalation: low-confidence reads are
                                    # surfaced for verification, not asserted as fact.
                                    "needs_review": p.get("confidence", 0.8) < ESCALATION_THRESHOLD,
                                    **{k: p[k] for k in DEEP_FIELDS if p.get(k) is not None},
                                },
                            )
                            for p in deduped
                        ]
                        db.add_all(events)
                        await db.commit()
                        total_plays = len(events)

                # ── Human escalation trigger (UATP) ────────────────────────
                if needs_review_count > 0:
                    await log_agent_action(
                        game_id=game_id, organization_id=str(org_id), job_id=job_id,
                        phase="escalation", level="escalation",
                        action=f"{needs_review_count} play(s) flagged for your review",
                        reason="These reads fell below my confidence threshold. I will not present them "
                               "as fact. Please verify them in the Play Log before game-planning around them.",
                        confidence=avg_conf,
                        detail={"needs_review": needs_review_count, "total_plays": total_plays,
                                "threshold": ESCALATION_THRESHOLD},
                    )

                # ── Completion (UATP success + confidence flag) ────────────
                await log_agent_action(
                    game_id=game_id, organization_id=str(org_id), job_id=job_id,
                    phase="complete", level="success",
                    action=f"Analysis complete — {total_plays} play(s) detected",
                    reason=f"Overall confidence: {confidence_band(avg_conf)}. "
                           f"{total_plays - needs_review_count} confident, {needs_review_count} flagged for review."
                           + (f" {failed_batches} segment(s) were skipped." if failed_batches else ""),
                    confidence=avg_conf,
                    detail={"total_plays": total_plays, "needs_review": needs_review_count,
                            "failed_batches": failed_batches},
                )

        except Exception as e:
            # UATP failure transparency — say WHY, never fail silently.
            logger.error(f"[ai_detect] game {game_id} failed: {e}")
            await log_agent_action(
                game_id=game_id, organization_id=str(org_id), job_id=job_id,
                phase="error", level="error",
                action="Detection stopped before completing",
                reason=f"I hit an error and stopped rather than guess: {str(e)[:300]}",
            )
            raise
        finally:
            # Always restore game to ready
            async with AsyncSessionLocal() as db:
                await db.execute(update(Game).where(Game.id == game_id).values(status="ready"))
                await db.commit()

        logger.info(f"[ai_detect] game {game_id}: {total_plays} plays auto-detected")
        return {"game_id": game_id, "plays_detected": total_plays,
                "needs_review": needs_review_count, "avg_confidence": avg_conf}

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
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

        # ALWAYS lay down a uniform interval grid and merge it with scene frames.
        # Scene-cut frames alone cluster on broadcast cuts/replays and miss most
        # snaps (a sparse 1-frame-per-11s on long film). The grid guarantees no
        # coverage gap larger than FALLBACK_INTERVAL so every snap window is sampled.
        scene_count = len(frames)
        interval_dir = os.path.join(output_dir, "interval")
        os.makedirs(interval_dir, exist_ok=True)
        # ffmpeg's fps filter needs a clean rate. "1/2.0" is REJECTED by ffmpeg;
        # pass an explicit decimal (e.g. 0.5 fps = one frame every 2s).
        rate = 1.0 / FALLBACK_INTERVAL
        logger.info(f"[ai_detect] {scene_count} scene frames — adding uniform grid at {rate:.4f} fps (every {FALLBACK_INTERVAL}s)")
        proc = subprocess.run([
            "ffmpeg", "-y", "-ss", str(SKIP_START_SECONDS), "-i", video_source,
            "-vf", f"fps={rate:.5f}", "-q:v", "3",
            os.path.join(interval_dir, "frame_%06d.jpg"),
        ], capture_output=True, text=True, timeout=1800)
        ifiles = sorted(
            os.path.join(interval_dir, f) for f in os.listdir(interval_dir) if f.endswith(".jpg")
        )
        logger.info(f"[ai_detect] uniform grid produced {len(ifiles)} interval frames")
        for i, f in enumerate(ifiles):
            frames.append((f, SKIP_START_SECONDS + i * FALLBACK_INTERVAL))

        frames.sort(key=lambda x: x[1])
        merged = len(frames)

        # Cap total frames to control cost; sample evenly across the game.
        if len(frames) > MAX_FRAMES:
            step = len(frames) // MAX_FRAMES
            frames = frames[::step][:MAX_FRAMES]

        # Persistent diagnostics (survive in the DB agent log; worker logs roll off).
        self._extract_diag = {
            "code_version": CODE_VERSION,
            "scene_frames": scene_count,
            "interval_frames": len(ifiles),
            "interval_rc": proc.returncode,
            "merged_pre_cap": merged,
            "final_frames": len(frames),
            "ffmpeg_err": ((proc.stderr or "")[-300:] if not ifiles else None),
        }
        return frames

    def _cluster_frames(self, frames: list, min_gap_seconds: float = CLUSTER_GAP_SECONDS) -> list:
        """Drop frames closer together than min_gap_seconds (same-moment duplicates)
        while preserving distinct play opportunities across the game.

        NOTE: frames here are (path, time_seconds) tuples — the real timestamp comes
        from ffmpeg showinfo, not the filename, so we cluster on the actual time.
        """
        if not frames:
            return frames
        ordered = sorted(frames, key=lambda ft: ft[1])
        kept = [ordered[0]]
        for ft in ordered[1:]:
            if ft[1] - kept[-1][1] >= min_gap_seconds:
                kept.append(ft)
        return kept

    def _frame_blocks(self, path: str, frame_no: int) -> list:
        """Return Claude content blocks for one frame: the full image PLUS upscaled
        crops of the upper and lower regions where the broadcast score/down-distance
        graphic usually sits. The full frame loses overlay legibility once Vision
        downsamples it; the zoomed crops keep the small digits readable.
        """
        blocks = []
        with open(path, "rb") as f:
            full = base64.standard_b64encode(f.read()).decode()
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": full}})
        try:
            import io
            from PIL import Image
            img = Image.open(path).convert("RGB")
            w, h = img.size
            # Score bugs live in the lower bar or the upper bar depending on broadcast.
            regions = [("lower", (0, int(h * 0.74), w, h)), ("upper", (0, 0, w, int(h * 0.16)))]
            for label, box in regions:
                crop = img.crop(box)
                crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
                buf = io.BytesIO()
                crop.save(buf, format="JPEG", quality=92)
                data = base64.standard_b64encode(buf.getvalue()).decode()
                blocks.append({"type": "text", "text": f"Frame {frame_no} {label} score/overlay zone (zoomed 2x for legibility):"})
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        except Exception as e:
            logger.warning(f"[ai_detect] overlay crop failed for {path}: {e}")
        return blocks

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
            content.append({"type": "text", "text": f"Frame {i + 1} (timestamp {int(t)}s):"})
            content.extend(self._frame_blocks(path, i + 1))

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
            if p.get("confidence", 0) < MIN_CONFIDENCE:
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

    def _derive_from_sequence(self, plays: list[dict]) -> list[dict]:
        """Fill yards_gained / result from the down-and-distance progression.

        When two consecutive offensive plays show the down incrementing within the
        same series (e.g. 1st & 10 then 2nd & 7), the yardage is EXACT (10-7 = 3).
        This is far more reliable than asking the model to read yardage off a still.
        Only fills values that are missing; never overwrites a real read.
        """
        plays = sorted(plays, key=lambda p: p.get("time_seconds") or 0)
        n = len(plays)

        def is_off(p):
            return (p.get("side") or "offense") == "offense"

        for i, p in enumerate(plays):
            if not is_off(p) or p.get("down") is None or p.get("distance") is None:
                continue
            d_i, dist_i = p["down"], p["distance"]
            # next offensive play in the same possession
            q = None
            for j in range(i + 1, n):
                nj = plays[j]
                if ((nj.get("time_seconds") or 0) - (p.get("time_seconds") or 0)) > 180:
                    break
                if (nj.get("side") or "offense") == "defense":
                    break  # possession changed — can't chain
                if is_off(nj) and nj.get("down") is not None:
                    q = nj
                    break
            if not q:
                continue
            d_j, dist_j = q.get("down"), q.get("distance")
            if d_j == d_i + 1 and dist_j is not None:
                gained = dist_i - dist_j  # exact: distance-to-go dropped by the gain
                if -30 <= gained <= 40:
                    if p.get("yards_gained") is None:
                        p["yards_gained"] = gained
                        p["yards_source"] = "derived"
                    if not p.get("result"):
                        p["result"] = "Loss" if gained < 0 else "Gain"
            elif d_j == 1 and (dist_j in (10, None)) and not p.get("result"):
                p["result"] = "First Down"  # series reset = they converted
        return plays

    def _derive_field_position(self, plays: list[dict]) -> list[dict]:
        """Derive field_position by chaining from any readable anchor + yards gained.

        field_position is a STRING here ("OWN 32" / "OPP 14" / "MID 50"), so we map it
        to an absolute 0-100 yardline (own goal = 0, midfield = 50, opp goal = 100),
        advance by yards_gained down a drive, and map back. We only chain within an
        offensive series and reset on possession change or unknown yardage, so we never
        invent a position we can't justify. Derived spots are flagged.
        """
        def to_abs(fp):
            if not fp:
                return None
            s = str(fp).upper().strip()
            m = re.match(r"(OWN|OPP)\s*(\d{1,2})", s)
            if m:
                n = int(m.group(2))
                return n if m.group(1) == "OWN" else 100 - n
            if s.startswith("MID") or s == "50":
                return 50
            return None

        def to_str(a):
            a = max(1, min(99, int(round(a))))
            if a == 50:
                return "MID 50"
            return f"OWN {a}" if a < 50 else f"OPP {100 - a}"

        plays = sorted(plays, key=lambda p: p.get("time_seconds") or 0)
        cur = None  # current absolute yardline at the start of this play
        for p in plays:
            if (p.get("side") or "offense") == "defense":
                cur = None  # possession flipped — offense spot no longer chains
                continue
            real = to_abs(p.get("field_position"))
            if real is not None:
                cur = real  # anchor from a real read
            elif cur is not None and p.get("field_position") is None:
                p["field_position"] = to_str(cur)
                p["field_position_derived"] = True
            # advance to the next play's starting spot using this play's yardage
            y = p.get("yards_gained")
            if cur is not None and y is not None:
                cur = max(1, min(99, cur + y))
            elif y is None:
                cur = None  # unknown gain → can't place the next spot
        return plays

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
