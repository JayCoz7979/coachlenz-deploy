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
import shutil
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
CODE_VERSION = "multipass-v4-costguard"

# Parallel ranged extraction: one long fps=0.5 pass over a 2.75h stream times out
# silently. Instead decode many short windows concurrently, each its own ffmpeg.
WINDOW_SIZE = 300          # seconds per window (5 min)
FRAMES_PER_WINDOW = 40     # default / back-compat -> 1 frame / 7.5s
# Recall tuning: denser sampling catches more snaps. Tuned by mode so DEEP (3 calls
# per batch) does not blow up cost. FAST is one cheap call per batch, so it can afford
# more frames for better recall.
FRAMES_PER_WINDOW_FAST = 66  # ~1 frame / 4.5s
FRAMES_PER_WINDOW_DEEP = 50  # ~1 frame / 6s
PARALLEL_JOBS = 6          # concurrent ffmpeg processes
JOB_TIMEOUT = 300          # per-window timeout (s); a stuck window fails alone, not the whole job

# ── Multi-pass vision (depth past single-prompt detection) ─────────────────────
# Pass 1 reads the pre-snap picture, Pass 2 enriches post-snap, Pass 3 (Opus)
# adversarially verifies low-confidence reads. Model-tiering keeps cost sane.
MULTIPASS_ENABLED = True
DETECT_MODEL = "claude-sonnet-4-6"   # bulk passes (volume)
VERIFY_MODEL = "claude-opus-4-8"     # hardest reads only (the tie-breaker)
VERIFY_CONFIDENCE_THRESHOLD = 0.65   # merged plays below this get an Opus second look
MAX_VERIFY_PER_BATCH = 3             # cap Opus calls per batch (cost guardrail)
# Concurrency for the vision pass. Segments run in parallel instead of one-at-a-time.
# DEEP makes 2-3 calls per segment, so fewer run at once to respect rate limits.
PARALLEL_VISION_FAST = 8
PARALLEL_VISION_DEEP = 4
# Cost guard: hard cap on segments analyzed per run so one long film can't blow the
# API budget. Over the cap, segments are thinned EVENLY across the whole film (still
# start-to-finish coverage, just lower density) rather than truncated. A coach can
# pass full=true to bypass it for a game that matters.
MAX_SEGMENTS_PER_RUN = 150


def _build_team_context(scout_jersey: Optional[str], opponent_jersey: Optional[str]) -> str:
    """Preamble that tells the vision agent which team is which, by appearance, so
    offense/defense is tied to the SCOUTED team consistently. Empty when no jersey
    info is set (the agent falls back to best-guess, as before)."""
    scout = (scout_jersey or "").strip()
    opp = (opponent_jersey or "").strip()
    if not scout and not opp:
        return ""
    lines = ["TEAM ATTRIBUTION — read this FIRST; it determines offense vs defense on every play:"]
    if scout:
        lines.append(f"- The team you are SCOUTING wears: {scout}.")
    if opp:
        lines.append(f"- Their OPPONENT wears: {opp}.")
    lines.append("- Use these colors to decide who has the ball on EVERY play, and be consistent across the whole film.")
    lines.append("- side=\"offense\" ONLY when the SCOUTED team has the ball. side=\"defense\" when the SCOUTED team is defending (opponent has the ball).")
    lines.append("- If you genuinely cannot tell the colors apart on a play, set side to your best read and note it in blind_spot.")
    return "\n".join(lines) + "\n\n"


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

PRE-SNAP MICRO-TELLS (ONLY when the camera is tight enough to actually see the linemen up close — All-22 / end-zone / sideline coaches' film. If the shot is a wide press-box angle where linemen are tiny, set ALL of these to null — do NOT guess):
- ol_stance: offensive line's dominant stance — "Heavy 3-Point" (weight forward, run lean), "Light 3-Point", "2-Point" (pass lean), "Mixed", null
- ol_hand_weight: weight on the down linemen's hands — "Heavy/Forward" (run lean), "Balanced", "Light/Back" (pass lean), null
- ol_splits: offensive line splits — "Tight", "Normal", "Wide", null
- key_pre_snap_tell: ONE sentence naming the single most telling pre-snap cue you can actually see (e.g. "Right guard in a heavy stance, weight rolled forward onto his hand, leaning into the run"), or null
- db_leverage: primary corner leverage on the key matchup — "Inside", "Outside", "Head-up", null
- lb_depth_tell: linebacker depth / movement — "Walked Up", "Stacked Tight", "Off/Depth", "Creeping (blitz tell)", null
- safety_depth_tell: pre-snap safety depth — "Single-High Deep", "Two-High Deep", "Rolled Down", "Cheating Down (run/blitz tell)", null

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

SPECIAL TEAMS DEEP EXTRACTION (when side=special_teams):
- st_unit: "Punt", "Punt Return", "Kickoff", "Kick Return", "Field Goal", "PAT", "Two-Point", "Onside Kick", null
- kick_direction: "Left", "Middle", "Right", null — which way the punt/kickoff was placed
- kick_result: "Touchback", "Fair Catch", "Returned", "Downed Inside 20", "Out of Bounds", "Muffed", "Blocked", "Made", "Missed", "Recovered", null
- return_scheme: "Middle Return", "Left Wall", "Right Wall", "Reverse", "Wedge", "No Return", null
- coverage_result: "Tackle in Coverage", "Big Return Allowed", "TD Allowed", "Contained", "Fair Catch Forced", null
- fg_distance_yds: estimated field-goal distance in yards (integer) if Field Goal, else null
- snap_quality: "Clean", "High", "Low", "Bobbled", null
- block_attempt: true if the defense rushed hard to block the kick, false otherwise
- st_fake: true if this kicking down turned into a fake/trick (fake punt, fake FG, pooch, surprise onside), false otherwise

Return ONLY valid JSON, nothing else:
{"plays": [{"side": "offense", "frame": 1, "down": null, "distance": null, "field_position": null, "formation": null, "play_type": null, "personnel": null, "result": null, "yards_gained": null, "confidence": 0.8, "blind_spot": null, "hash_position": null, "motion": false, "motion_type": null, "receiver_alignment": null, "run_direction": null, "run_gap": null, "run_concept": null, "pass_concept": null, "pass_depth": null, "target_area": null, "tempo": null, "score_situation": null, "play_description": null, "is_play_action": false, "screen_subtype": null, "goal_line": false, "defensive_front": null, "coverage": null, "coverage_shell": null, "safety_rotation": null, "corner_technique": null, "blitz": null, "pressure_type": null, "pressure_gap": null, "linebacker_alignment": null, "ol_stance": null, "ol_hand_weight": null, "ol_splits": null, "key_pre_snap_tell": null, "db_leverage": null, "lb_depth_tell": null, "safety_depth_tell": null, "players": [], "primary_player_jersey": null, "st_unit": null, "kick_direction": null, "kick_result": null, "return_scheme": null, "coverage_result": null, "fg_distance_yds": null, "snap_quality": null, "block_attempt": false, "st_fake": false}]}

If zero plays: {"plays": []}"""


# ── Multi-pass prompts ─────────────────────────────────────────────────────────
# PASS 1: segment the plays and read ONLY the pre-snap picture deeply. We do not
# ask about the result here — a focused prompt reads formation/alignment/tells far
# better than one overloaded prompt trying to do everything at once.
DETECTION_PROMPT_PRESNAP = """You are the best pre-snap film analyst alive — better than any college or NFL quality-control coach. The frames below are consecutive moments of game film in time order. Each frame also includes two zoomed crops of the score/overlay zones for reading the down-and-distance bug.

YOUR ONLY JOB IN THIS PASS: find every DISTINCT football play in this window and read the PRE-SNAP picture for each. Do NOT judge the result yet — another pass handles that.

Identify each distinct snap (run, pass, screen, RPO, option, punt, FG, PAT, kickoff). Skip huddles, timeouts, sideline shots, replays, commercials, dead time.

For each play, assign a sequential play_index starting at 0 (0,1,2…) in time order — this is the KEY that the post-snap pass uses to match your read, so it MUST be present and stable.

Read from the PRE-SNAP frames (offense set at the line). Extract:
- play_index: 0-based sequential integer (REQUIRED)
- frame: the frame NUMBER showing the best pre-snap look (REQUIRED)
- side: "offense" | "defense" | "special_teams"
- down, distance, field_position, hash_position: from the score bug + field. null if truly unreadable — never guess.
- formation: "Shotgun","I-Form","Pistol","Singleback","Empty","Trips","Bunch","Wildcat","Ace","Offset I","Pro Set","Other"
- personnel: back/TE count e.g. "11","12","21","10" if countable, else null
- receiver_alignment: "Trips Right","Twins Left","Bunch","2x2","3x1","Empty","Tight", null
- motion: true/false, motion_type: "Jet","Orbit","Shift","Across","Return","None"
- defensive_front: "4-3","3-4","4-2-5","Bear","Nickel","Dime","Goal Line","Even","Odd", null
- coverage_shell: pre-snap shell ONLY (what the safeties show before the snap): "1-high","2-high","0-high","Quarters look","Press","Off", null
- db_leverage: "Inside","Outside","Press","Off","Mixed", null — corner leverage on the receivers
- lb_depth_tell: "Walked up","Stacked","Depth","Creeping", null
- safety_depth_tell: "Rolled down","Deep middle","Two deep","Robber", null
PRE-SNAP MICRO-TELLS — ONLY if the camera is tight enough to actually see a lineman's hand and stance. On a wide press-box or end-zone angle you CANNOT see these — set them to null and say so in blind_spot. Never invent them.
- ol_stance: "Heavy (weight forward)","Light (weight back)","Balanced","Mixed", null
- ol_hand_weight: "Knuckles white / loaded","Light fingertips","Hand off ground","Mixed", null
- ol_splits: "Tight","Normal","Wide","Uneven", null
- key_pre_snap_tell: one short phrase naming the single biggest pre-snap giveaway, or null
- st_unit: "Punt","Kickoff","Field Goal","PAT","Two-Point","Onside Kick", null (special teams only)
- confidence: 0-1, your confidence in THIS pre-snap read
- blind_spot: what the camera/angle prevented you from seeing, or null

Return ONLY JSON: {"plays": [{"play_index": 0, "frame": 1, "side": "offense", ...}]}
If zero plays: {"plays": []}"""


# PASS 2: given Pass 1's plays, read ONLY what happened AFTER the snap. Returns the
# SAME plays (same play_index, same order) enriched — keeps the play set aligned.
DETECTION_PROMPT_POSTSNAP = """You are the best post-snap film analyst alive. The frames below are the SAME consecutive moments of game film, in time order.

A pre-snap pass already segmented the plays in this window. Here they are (match your reads to these by play_index — return the SAME plays, SAME play_index, SAME count, do not invent or drop any):

{presnap_plays}

YOUR ONLY JOB: for each play above, read what happened AFTER the snap from the at-snap and post-play frames. Use the SEQUENCE across frames, never a single still.

For each play return:
- play_index: echo the matching index from the list above (REQUIRED)
- play_type: "Run","Pass","Screen","Draw","RPO","QB Run","Option","Punt","Field Goal","Kickoff","PAT","Two-Point", null
- run_pass: "Run" | "Pass" | null (the fundamental call)
- run_gap: "A","B","C","D/Edge", null  | run_direction: "Left","Right","Middle", null
- run_concept: "Inside Zone","Outside Zone","Power","Counter","Trap","Duo","Sweep","Toss","Dive", null
- pass_concept: "Slant-Flat","Mesh","Smash","Four Verts","Stick","Curl-Flat","Y-Cross","Screen", null
- pass_depth: "Behind LOS","Short (1-9)","Intermediate (10-19)","Deep (20+)", null
- target_area: "Left flat","Left seam","Middle","Right seam","Right flat","Backfield", null
- is_play_action: true/false  | screen_subtype: "Bubble","Tunnel","RB Screen","Slip","Jailbreak", null
- coverage: the coverage actually PLAYED after the snap (may differ from the shell): "Cover 0/1/2/3/4/6","Man","Zone","Match", null
- blitz: true/false  | pressure_type: "A-gap","Edge","Corner","Zone blitz","None", null  | pressure_gap: "A","B","C","Edge", null
- ball_carrier_jersey / primary_player_jersey: visible jersey number of the main ball-handler, or null
- players: [{"jersey": "12", "role": "QB"}] for any clearly identifiable players, else []
- result: "Gain","Loss","First Down","Touchdown","Incomplete","Sack","Turnover","No Gain","Made","Missed", null
- yards_gained: integer if visibly clear from the frames, else null (a later step derives it from down progression)
- st_unit / kick_direction / kick_result / return_scheme / fg_distance_yds / st_fake: special teams only, else null
- confidence: 0-1, your confidence in THIS post-snap read

Return ONLY JSON: {"plays": [{"play_index": 0, "play_type": ..., ...}]}"""


# PASS 3: Opus adversarially verifies ONE low-confidence merged play.
VERIFY_PROMPT = """You are the sharpest, most skeptical film reviewer in football. An automated system produced this play read from the frames below. Your job is to REFUTE or CONFIRM it — assume it may be wrong.

Candidate read:
{candidate}

Look at the frames carefully. Correct any field you can clearly see is wrong, and ONLY change a field if the film actually supports a different value — otherwise leave it. Be honest about what the camera cannot show.

Return ONLY JSON with the fields you are confident about plus a final judgment:
{{"down": ..., "distance": ..., "formation": ..., "play_type": ..., "run_pass": ..., "coverage": ..., "result": ..., "yards_gained": ..., "confidence": 0.0, "verdict": "confirmed" | "corrected" | "unreadable", "note": "one short sentence on what you changed or why you trust it"}}
Set confidence to your HONEST final confidence after looking. Use null for anything the film cannot support."""


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
        # "fast" = single focused pass (~1x cost), "deep" = 3-pass engine (~3x cost).
        # Default fast to protect API spend; deep is opt-in for games that matter.
        mode = (payload.get("detection_mode") or "fast").lower()
        self._multipass = MULTIPASS_ENABLED and mode == "deep"
        # Cost guard: bypassed only when the coach explicitly asks for full density.
        self._full_coverage = bool(payload.get("full"))
        return await self._detect_plays(game_id, dry_run=dry_run, job_id=job_id)

    async def _detect_plays(self, game_id: str, dry_run: bool = False, job_id=None) -> dict:
        # ── Load game ──────────────────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Game).where(Game.id == game_id))
            game = result.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            # "analyzing" is allowed too: a prior run may have set it and not finished
            # (re-run / orphan recovery). Only block genuinely un-ingested film.
            if game.status not in ("ready", "analyzing"):
                raise ValueError(f"Game not ready for detection (status={game.status})")
            sport = (game.sport or "football").lower()
            org_id = game.organization_id
            # Team attribution context for the vision prompts (which jerseys = scouted team).
            self._team_context = _build_team_context(game.scout_jersey, game.opponent_jersey)

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
                # Pre-flight: ensure room for the extracted frames.
                free_gb = shutil.disk_usage(frames_dir).free / 1e9
                if free_gb < 2.0:
                    raise RuntimeError(f"Insufficient disk for frame extraction: {free_gb:.1f}GB free, need 2GB")

                # Parallel ranged extraction — many short ffmpeg windows in parallel,
                # instead of one fps=0.5 pass over the whole stream (which timed out
                # silently and yielded 0 grid frames on long film).
                duration = await self._probe_duration(video_source, game.duration_seconds)
                # Denser sampling for recall; lighter in deep mode since each batch is 3 calls.
                fpw = FRAMES_PER_WINDOW_DEEP if getattr(self, "_multipass", False) else FRAMES_PER_WINDOW_FAST
                frame_paths = await self._extract_windows(video_source, duration, frames_dir, frames_per_window=fpw)
                # Snap-aware clustering: drop same-moment duplicates (no-op on the uniform
                # window grid, but harmless and protects against overlapping windows).
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

                # ── Cost guard ─────────────────────────────────────────────
                # Bound API spend per run. Over the cap, thin segments EVENLY across
                # the whole film (start-to-finish coverage, lower density) so one long
                # game can't surprise the budget. Coach opts into full=true to bypass.
                total_segments = len(batches)
                if not getattr(self, "_full_coverage", False) and total_segments > MAX_SEGMENTS_PER_RUN:
                    step = total_segments / MAX_SEGMENTS_PER_RUN
                    batches = [batches[int(i * step)] for i in range(MAX_SEGMENTS_PER_RUN)]
                    calls_per_seg = 3 if getattr(self, "_multipass", False) else 1
                    await log_agent_action(
                        game_id=game_id, organization_id=str(org_id), job_id=job_id,
                        phase="cost_guard", level="info",
                        action=f"Cost guard: analyzing {len(batches)} of {total_segments} segments (even sampling across the full film)",
                        reason=f"To stay within budget I sampled the whole game at lower density "
                               f"(~{len(batches) * calls_per_seg} vision calls). Re-run with Full coverage to analyze every segment.",
                        detail={"segments_analyzed": len(batches), "segments_total": total_segments,
                                "estimated_calls": len(batches) * calls_per_seg},
                    )

                # Log a heartbeat roughly every 10% of batches so the live panel
                # shows steady progress without flooding the log.
                log_every = max(1, len(batches) // 10)
                failed_batches = 0
                completed = 0
                # Process segments concurrently (was one-at-a-time). Bounded by a
                # semaphore so we stay within API rate limits; deep mode runs fewer at
                # once because each segment makes 2-3 calls.
                concurrency = PARALLEL_VISION_DEEP if getattr(self, "_multipass", False) else PARALLEL_VISION_FAST
                sem = asyncio.Semaphore(concurrency)

                async def process_batch(batch_idx, batch):
                    nonlocal failed_batches, completed
                    async with sem:
                        try:
                            plays = await self._analyze_batch(batch, batch_idx, len(batches), sport)
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
                            return
                        all_plays.extend(plays)  # safe: no await between read and append (single-threaded loop)
                        completed += 1
                        logger.info(f"[ai_detect] Batch {batch_idx+1}/{len(batches)}: {len(plays)} plays")
                        if plays and (completed % log_every == 0 or completed == len(batches)):
                            confs = [p.get("confidence", 0) for p in plays]
                            avg_c = round(sum(confs) / len(confs), 2) if confs else None
                            await log_agent_action(
                                game_id=game_id, organization_id=str(org_id), job_id=job_id,
                                phase="vision_analysis", level="info",
                                action=f"Analyzed {completed} of {len(batches)} segments — {len(plays)} play(s) in the latest",
                                reason=f"Reading play development across consecutive frames. "
                                       f"Segment confidence: {confidence_band(avg_c)}.",
                                confidence=avg_c,
                                detail={"completed": completed, "total_batches": len(batches),
                                        "plays_in_batch": len(plays)},
                            )

                await asyncio.gather(*[process_batch(i, b) for i, b in enumerate(batches)])

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
                            # Pre-snap micro-tells (tight/All-22 film)
                            "ol_stance", "ol_hand_weight", "ol_splits", "key_pre_snap_tell",
                            "db_leverage", "lb_depth_tell", "safety_depth_tell",
                            # Single-camera transparency (all sports)
                            "blind_spot",
                            # Player-level tracking (all sports)
                            "players", "primary_player_jersey",
                            # Derivation provenance
                            "yards_source", "field_position_derived",
                            # Special teams deep extraction
                            "st_unit", "kick_direction", "kick_result", "return_scheme",
                            "coverage_result", "fg_distance_yds", "snap_quality",
                            "block_attempt", "st_fake",
                            # Multi-pass engine (pre/post-snap split + Opus verify)
                            "run_pass", "ball_carrier_jersey",
                            "confidence_presnap", "confidence_postsnap",
                            "verified", "verdict", "verify_note",
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

    async def _probe_duration(self, url: str, fallback: Optional[int] = None) -> float:
        """True duration via ffprobe (falls back to the DB value)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
            dur = float((json.loads(out.decode() or "{}").get("format") or {}).get("duration", 0) or 0)
            if dur > 0:
                return dur
        except Exception as e:
            logger.warning(f"[ai_detect] ffprobe duration failed: {e}")
        if fallback:
            return float(fallback)
        raise RuntimeError("Could not determine video duration")

    async def _extract_window(self, url: str, start: float, dur: float, win_dir: str, idx: int,
                              frames_per_window: int = FRAMES_PER_WINDOW):
        """Decode ONE short window into frames_per_window evenly-spaced frames."""
        rate = frames_per_window / WINDOW_SIZE  # fps that spreads the frames across the whole window
        pattern = os.path.join(win_dir, f"w{idx:04d}_%06d.jpg")
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", url,
            # scale to 1600 keeps decode fast and the score-bug legible (Vision caps ~1568 anyway)
            "-vf", f"fps={rate:.5f},scale=1600:-2",
            "-q:v", "3", "-frames:v", str(frames_per_window), pattern,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=JOB_TIMEOUT)
            return proc.returncode, (err.decode()[-300:] if err else "")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return -1, f"TIMEOUT window {idx} start={start}"

    async def _extract_windows(self, url: str, total_duration: float, out_base: str,
                               frames_per_window: int = FRAMES_PER_WINDOW):
        """Parallel ranged extraction. Returns (path, time_seconds) tuples and stamps
        self._extract_diag so the DB proves coverage. Replaces the single fps=0.5 pass
        that timed out silently on long streams."""
        windows = []
        start = float(SKIP_START_SECONDS)
        while start < total_duration - 10:
            windows.append((start, min(WINDOW_SIZE, total_duration - start)))
            start += WINDOW_SIZE

        # Safety cap: keep total frames under MAX_FRAMES by thinning density on long film.
        if windows and frames_per_window * len(windows) > MAX_FRAMES:
            frames_per_window = max(10, MAX_FRAMES // len(windows))
        self._frames_per_window = frames_per_window

        sem = asyncio.Semaphore(PARALLEL_JOBS)

        async def run(idx, s, d):
            async with sem:
                win_dir = os.path.join(out_base, f"window_{idx:04d}")
                os.makedirs(win_dir, exist_ok=True)
                rc, err = await self._extract_window(url, s, d, win_dir, idx, frames_per_window)
                files = sorted(f for f in os.listdir(win_dir) if f.endswith(".jpg"))
                if rc != 0 or not files:
                    logger.error(f"[ai_detect] window {idx} FAILED rc={rc} frames={len(files)} start={s} err={err}")
                else:
                    logger.info(f"[ai_detect] window {idx} ok: {len(files)} frames @ {s}s")
                return (win_dir, s, rc, files, err)

        results = await asyncio.gather(*[run(i, s, d) for i, (s, d) in enumerate(windows)], return_exceptions=True)

        frames, ok, failed, first_err = [], 0, 0, None
        gap = WINDOW_SIZE / frames_per_window
        for r in results:
            if isinstance(r, Exception):
                failed += 1
                first_err = first_err or str(r)[:200]
                continue
            win_dir, wstart, rc, files, err = r
            if rc != 0 or not files:
                failed += 1
                first_err = first_err or err
                continue
            ok += 1
            for i, fn in enumerate(files):
                frames.append((os.path.join(win_dir, fn), wstart + i * gap))

        frames.sort(key=lambda ft: ft[1])
        if len(frames) > MAX_FRAMES:
            step = len(frames) // MAX_FRAMES
            frames = frames[::step][:MAX_FRAMES]

        self._extract_diag = {
            "code_version": CODE_VERSION, "method": "parallel_windows",
            "windows_total": len(windows), "windows_ok": ok, "windows_failed": failed,
            "total_frames": len(frames), "ffmpeg_err": first_err,
        }
        logger.info(f"[ai_detect] parallel extraction: {ok}/{len(windows)} windows ok, {len(frames)} frames")
        return frames

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

    def _frame_content(self, batch) -> list:
        """Shared Claude content blocks for a batch (full frame + zoomed overlay
        crops). Built once and reused across multi-pass calls — same images."""
        content = []
        for i, (path, t) in enumerate(batch):
            content.append({"type": "text", "text": f"Frame {i + 1} (timestamp {int(t)}s):"})
            content.extend(self._frame_blocks(path, i + 1))
        return content

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = (raw or "").strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except Exception:
            return {}

    async def _vision_json(self, client, model: str, content: list, max_tokens: int = 4096) -> dict:
        """One vision call -> parsed JSON dict ({} on parse failure)."""
        response = await client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return self._parse_json(response.content[0].text)

    def _assign_times(self, plays: list, batch) -> list:
        """Confidence-gate plays and stamp each with the REAL timestamp of the frame
        the model picked — never an AI-estimated time."""
        out = []
        for p in plays:
            if p.get("confidence", 0) < MIN_CONFIDENCE:
                continue
            fr = p.get("frame")
            if isinstance(fr, (int, float)) and 1 <= int(fr) <= len(batch):
                p["time_seconds"] = round(batch[int(fr) - 1][1])
            else:
                p["time_seconds"] = round(batch[len(batch) // 2][1])
            out.append(p)
        return out

    async def _analyze_batch(self, batch, batch_idx: int, total_batches: int, sport: str = "football") -> list[dict]:
        """Route a batch of frames to Claude Vision. Football uses the multi-pass
        engine (detect+pre-snap -> post-snap enrich -> Opus verify); other sports
        use the single focused prompt."""
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Per-run flag set from the job's detection_mode (falls back to the global).
        if getattr(self, "_multipass", MULTIPASS_ENABLED) and sport in ("football", "flag_football"):
            return await self._analyze_batch_multipass(client, batch, batch_idx)

        prompt = DETECTION_PROMPT_BASKETBALL if sport == "basketball" else DETECTION_PROMPT
        prompt = getattr(self, "_team_context", "") + prompt
        content = self._frame_content(batch) + [{"type": "text", "text": prompt}]
        parsed = await self._vision_json(client, DETECT_MODEL, content)
        return self._assign_times(parsed.get("plays", []), batch)

    # Pre-snap fields handed to the post-snap pass as alignment context.
    _PRESNAP_CTX_KEYS = (
        "play_index", "frame", "side", "down", "distance", "field_position",
        "formation", "personnel", "receiver_alignment", "st_unit",
    )
    # Fields the verify pass / post-snap pass may overwrite on a play.
    _VERIFY_KEYS = ("down", "distance", "formation", "play_type", "run_pass",
                    "coverage", "result", "yards_gained")

    async def _analyze_batch_multipass(self, client, batch, batch_idx: int) -> list[dict]:
        """Three-pass football detection. Pass 1 (pre-snap) segments + reads the
        pre-snap picture; Pass 2 (post-snap) enriches the SAME plays by play_index;
        Pass 3 (Opus) adversarially verifies only the low-confidence merges."""
        frames = self._frame_content(batch)

        # Pass 1 — detect + pre-snap
        p1 = await self._vision_json(client, DETECT_MODEL,
                                     frames + [{"type": "text", "text": getattr(self, "_team_context", "") + DETECTION_PROMPT_PRESNAP}])
        pre = p1.get("plays", [])
        if not pre:
            return []
        for i, pl in enumerate(pre):
            pl.setdefault("play_index", i)

        # Pass 2 — post-snap enrich, anchored to pass-1 plays
        ctx = json.dumps([{k: pl.get(k) for k in self._PRESNAP_CTX_KEYS} for pl in pre], default=str)
        p2 = {}
        try:
            post_resp = await self._vision_json(
                client, DETECT_MODEL,
                frames + [{"type": "text", "text": getattr(self, "_team_context", "") + DETECTION_PROMPT_POSTSNAP.replace("{presnap_plays}", ctx)}])
            p2 = {pl.get("play_index"): pl for pl in post_resp.get("plays", []) if pl.get("play_index") is not None}
        except Exception as e:
            logger.warning(f"[ai_detect] post-snap pass failed batch {batch_idx}: {e}")

        # Merge: post-snap fields layer onto the pre-snap play; confidence = mean.
        merged = []
        for pl in pre:
            post = p2.get(pl.get("play_index"), {})
            m = dict(pl)
            for k, v in post.items():
                if v is not None and k != "play_index":
                    m[k] = v
            c_pre = float(pl.get("confidence") or 0.7)
            c_post = post.get("confidence")
            m["confidence_presnap"] = c_pre
            m["confidence_postsnap"] = c_post
            m["confidence"] = round((c_pre + float(c_post)) / 2, 2) if c_post is not None else c_pre
            merged.append(m)

        # Pass 3 — Opus verifies the shakiest reads (capped for cost)
        weak = sorted((m for m in merged if m["confidence"] < VERIFY_CONFIDENCE_THRESHOLD),
                      key=lambda m: m["confidence"])[:MAX_VERIFY_PER_BATCH]
        for m in weak:
            cand = json.dumps({k: m.get(k) for k in self._VERIFY_KEYS}, default=str)
            try:
                v = await self._vision_json(
                    client, VERIFY_MODEL,
                    frames + [{"type": "text", "text": VERIFY_PROMPT.format(candidate=cand)}],
                    max_tokens=1024)
            except Exception as e:
                logger.warning(f"[ai_detect] verify pass failed batch {batch_idx}: {e}")
                continue
            if not v:
                continue
            for k in self._VERIFY_KEYS:
                if v.get(k) is not None:
                    m[k] = v[k]
            if v.get("confidence") is not None:
                m["confidence"] = round(float(v["confidence"]), 2)
            m["verified"] = True
            m["verdict"] = v.get("verdict")
            m["verify_note"] = v.get("note")

        return self._assign_times(merged, batch)

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
