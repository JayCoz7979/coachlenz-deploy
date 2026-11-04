"""
Basketball possession-context + review layer (FLAG-GATED, DEFAULT OFF).

Runs AFTER the existing single detection pass. It does NOT replace or alter the
shipped pipeline: it is a deterministic, read-only reconstruction built strictly
from DETECTED events. It is not wired into the worker; it is gated by
BB_POSSESSION_CONTEXT_ENABLED (default off) and exposed through
maybe_build_possession_context().

Hard rules honored here:
- Deterministic. Every value is anchored to a detected event. Nothing is
  synthesized. Where evidence is missing, the value is "unknown" or a gap is
  flagged, never filled with a plausible-looking fact.
- No OCR / no inference / no provider calls anywhere in this module.
- Pure stdlib, so the whole layer is testable fully offline with no deps.

Four pieces:
  1. build_possession_context(events)  -> possession sequence from detected events
  2. build_review_queue(events)        -> uncertain candidates, NOT promoted
  3. plan_review_pass / run_review_pass -> a targeted second-look CODE PATH that
                                           never spends and never auto-runs
  4. dedup_basketball_actions(plays)   -> action-aware dedup that keeps distinct
                                           actions inside the 3s window

Event accessor works on both dicts (detected plays, pre-persist) and ORM Event
objects (attribute + extra_data), so callers can use either.
"""
import os
from typing import Any, Callable, Optional

POSSESSION_CONTEXT_VERSION = "bb-possession-v1"

# Confidence policy mirrors backend.services.agent_log (kept local so this module
# has zero heavy imports and runs offline). HARD_FLOOR: below this a read is
# discarded upstream. ESCALATION_THRESHOLD: below this a read is "needs review".
HARD_FLOOR = 0.5
ESCALATION_THRESHOLD = 0.65
# Default confidence used when a detected event carries none, matching the worker's
# persistence default.
_DEFAULT_CONFIDENCE = 0.8

# Mirrors DEDUP_WINDOW_SECONDS_BASKETBALL in worker_ai_detect. Two observations
# closer than this MAY be the same action; identity evidence decides.
BB_DEDUP_WINDOW = 3.0

# Flagged events within this many seconds are grouped into one review segment.
REVIEW_SEGMENT_GAP = 12.0

_MADE_RESULTS = ("made", "good", "and-1")


# ── flag gate ────────────────────────────────────────────────────────────────
def possession_context_enabled() -> bool:
    """Config flag, DEFAULT OFF. Nothing in the shipped pipeline reads this; it
    exists so the layer can be turned on deliberately once it is wired + proven."""
    return os.getenv("BB_POSSESSION_CONTEXT_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


# ── event accessor (dict or ORM Event) ───────────────────────────────────────
def _field(ev: Any, key: str, default: Any = None) -> Any:
    if isinstance(ev, dict):
        if ev.get(key) is not None:
            return ev[key]
        ed = ev.get("extra_data")
        if isinstance(ed, dict) and ed.get(key) is not None:
            return ed[key]
        return default
    val = getattr(ev, key, None)
    if val is not None:
        return val
    ed = getattr(ev, "extra_data", None)
    if isinstance(ed, dict) and ed.get(key) is not None:
        return ed[key]
    return default


def _confidence(ev: Any) -> float:
    c = _field(ev, "confidence", None)
    try:
        return float(c) if c is not None else _DEFAULT_CONFIDENCE
    except (TypeError, ValueError):
        return _DEFAULT_CONFIDENCE


def _team(ev: Any) -> str:
    """Team in possession, from the DETECTED side. side is relative to the scouted
    team: offense/transition = scouted team has the ball, defense = opponent."""
    side = (_field(ev, "side", "offense") or "offense").strip().lower()
    if side == "defense":
        return "opponent"
    if side in ("offense", "transition"):
        return "scouted"
    return "unknown"


def _is_made_shot(ev: Any) -> bool:
    return (_field(ev, "event_type", "") or "").lower() == "shot" and \
        (_field(ev, "result", "") or "").lower() in _MADE_RESULTS


def _is_possession_ending(ev: Any) -> bool:
    """A detected event that ends the current team's possession. Deterministic,
    from detected fields only: a made shot, a turnover, or a steal (ball taken)."""
    et = (_field(ev, "event_type", "") or "").lower()
    if et in ("turnover", "steal"):
        return True
    return _is_made_shot(ev)


def _time(ev: Any) -> Optional[float]:
    t = _field(ev, "time_seconds", None)
    try:
        return float(t) if t is not None else None
    except (TypeError, ValueError):
        return None


def _sorted_by_time(events: list) -> list:
    # None times sort last, order otherwise stable.
    return sorted(events, key=lambda e: (_time(e) is None, _time(e) if _time(e) is not None else 0.0))


def _event_ref(ev: Any) -> dict:
    """Compact, serializable snapshot of a detected event. Detected fields only."""
    return {
        "time_seconds": _time(ev),
        "event_type": _field(ev, "event_type"),
        "side": _field(ev, "side"),
        "result": _field(ev, "result"),
        "player": _field(ev, "player") or _field(ev, "primary_player_jersey") or _field(ev, "ball_carrier_jersey"),
        "quarter": _field(ev, "quarter"),
        "confidence": _confidence(ev),
    }


# ── 1. possession reconstruction ──────────────────────────────────────────────
def build_possession_context(events: list) -> dict:
    """Reconstruct the possession sequence from DETECTED events only.

    Rules (all anchored to detected fields):
      - Team in possession comes from the detected `side`.
      - A new possession starts when the team changes, OR when a same-team event
        follows a detected possession-ending event (made shot / turnover / steal).
        In the second case the opponent's possession was NOT detected, so the new
        possession is flagged undetected_possession_gap_before=True. The missing
        opponent possession is NOT invented.
      - quarter is the tagged quarter where member events carry one; if none carry
        it, quarter is "unknown"; if they disagree it is "mixed".
      - score_margin / shot_clock_range are surfaced only where tagged.
      - confidence is summarized from member events; low_confidence marks a
        possession whose mean confidence is below the review threshold.
    """
    ordered = _sorted_by_time(events)
    possessions: list = []
    cur: Optional[dict] = None

    def _open(ev, gap_before=False):
        return {
            "team": _team(ev),
            "_members": [ev],
            "ended": _is_possession_ending(ev),
            "ending": _ending_label(ev),
            "undetected_possession_gap_before": gap_before,
        }

    for ev in ordered:
        team = _team(ev)
        if cur is None:
            cur = _open(ev)
        elif team != cur["team"]:
            possessions.append(cur)
            cur = _open(ev)
        elif cur["ended"]:
            # same team again, right after a possession-ender -> opponent's
            # possession between them was not detected. Flag it, never invent it.
            possessions.append(cur)
            cur = _open(ev, gap_before=True)
        else:
            cur["_members"].append(ev)
            if _is_possession_ending(ev):
                cur["ended"] = True
                cur["ending"] = _ending_label(ev)
    if cur is not None:
        possessions.append(cur)

    out = [_finalize_possession(i, p) for i, p in enumerate(possessions)]
    return {
        "version": POSSESSION_CONTEXT_VERSION,
        "deterministic": True,
        "possessions": out,
        "summary": _summarize(out),
        "disclaimer": (
            "Reconstructed strictly from detected events. A possession with no "
            "detected opponent sequence before it is marked as a gap, not invented. "
            "Quarter, score, and clock are shown only where the model tagged them; "
            "everything else is 'unknown'."
        ),
    }


def _ending_label(ev: Any) -> Optional[str]:
    et = (_field(ev, "event_type", "") or "").lower()
    if et == "turnover":
        return "turnover"
    if et == "steal":
        return "steal"
    if _is_made_shot(ev):
        return "made_shot"
    return None


def _finalize_possession(index: int, p: dict) -> dict:
    members = p["_members"]
    confs = [_confidence(e) for e in members]
    mean_conf = round(sum(confs) / len(confs), 3) if confs else None
    quarters = sorted({_field(e, "quarter") for e in members if _field(e, "quarter") is not None})
    if not quarters:
        quarter: Any = "unknown"
    elif len(quarters) == 1:
        quarter = quarters[0]
    else:
        quarter = "mixed"
    times = [_time(e) for e in members if _time(e) is not None]
    return {
        "index": index,
        "team": p["team"],
        "quarter": quarter,
        "start_time": min(times) if times else None,
        "end_time": max(times) if times else None,
        "event_count": len(members),
        "events": [_event_ref(e) for e in members],
        "ending": p["ending"] or "unknown",
        "mean_confidence": mean_conf,
        "min_confidence": round(min(confs), 3) if confs else None,
        "low_confidence": (mean_conf is not None and mean_conf < ESCALATION_THRESHOLD),
        "undetected_possession_gap_before": p["undetected_possession_gap_before"],
        "score_margin": _first_tagged(members, "score_margin"),
        "shot_clock_range": _first_tagged(members, "shot_clock_range"),
    }


def _first_tagged(members: list, key: str) -> Any:
    for e in members:
        v = _field(e, key)
        if v is not None:
            return v
    return None


def _summarize(possessions: list) -> dict:
    quarters = sorted({p["quarter"] for p in possessions if isinstance(p["quarter"], int)})
    return {
        "total_possessions": len(possessions),
        "scouted": sum(1 for p in possessions if p["team"] == "scouted"),
        "opponent": sum(1 for p in possessions if p["team"] == "opponent"),
        "unknown_team": sum(1 for p in possessions if p["team"] == "unknown"),
        "quarters_detected": quarters,
        "undetected_possession_gaps": sum(1 for p in possessions if p["undetected_possession_gap_before"]),
        "low_confidence_possessions": sum(1 for p in possessions if p["low_confidence"]),
    }


def maybe_build_possession_context(events: list) -> Optional[dict]:
    """Flag-gated entrypoint. Returns None when the flag is OFF (the default), so a
    caller can wire this after the single pass without changing shipped behavior
    until the flag is deliberately enabled.

    When on, it returns the possession reconstruction PLUS the review queue in one
    serializable blob, so a single consumer (the report, the scout response) has
    everything the coach-facing review screen needs without a second call. The
    review candidates are the uncertain detections surfaced for a human look; they
    are NOT promoted to confirmed events.
    """
    if not possession_context_enabled():
        return None
    ctx = build_possession_context(events)
    ctx["review_candidates"] = build_review_queue(events)
    return ctx


# ── 2. review queue (uncertain candidates, never promoted) ────────────────────
def build_review_queue(events: list) -> list:
    """Return the uncertain detections as review candidates WITHOUT promoting them
    to confirmed events and WITHOUT changing the events. An event is a candidate
    when its confidence sits in the gray band [HARD_FLOOR, ESCALATION_THRESHOLD).

    Candidate shape:
      {
        "status": "pending_review",          # never "confirmed"
        "reason": "confidence_below_threshold",
        "confidence": float,
        "band": "low" | "medium",
        "event": { detected-fields-only snapshot },
      }
    """
    queue = []
    for ev in _sorted_by_time(events):
        c = _confidence(ev)
        if HARD_FLOOR <= c < ESCALATION_THRESHOLD:
            queue.append({
                "status": "pending_review",
                "reason": "confidence_below_threshold",
                "confidence": round(c, 3),
                "band": "medium" if c >= ESCALATION_THRESHOLD else "low",
                "event": _event_ref(ev),
            })
    return queue


# ── 3. targeted review-pass PATH (never spends, never auto-runs) ──────────────
def plan_review_pass(candidates: list, config: Optional[dict] = None) -> dict:
    """Plan a second look at ONLY the flagged segments. Pure planning: it makes no
    provider call and moves no money. Nearby flagged candidates are grouped into
    review segments. budget_cap is a passthrough PLACEHOLDER from config; no dollar
    threshold is invented and no spend is enabled.
    """
    cfg = config or {}
    timed = sorted(
        (c for c in candidates if c.get("event", {}).get("time_seconds") is not None),
        key=lambda c: c["event"]["time_seconds"],
    )
    segments: list = []
    for c in timed:
        t = c["event"]["time_seconds"]
        if segments and t - segments[-1]["end"] <= REVIEW_SEGMENT_GAP:
            seg = segments[-1]
            seg["end"] = t
            seg["event_count"] += 1
            seg["times"].append(t)
        else:
            segments.append({"start": t, "end": t, "event_count": 1, "times": [t]})
    return {
        "status": "planned_not_executed",
        "segments": segments,
        "planned_calls": len(segments),
        "budget_cap": cfg.get("budget_cap"),  # placeholder; None unless a caller sets one
        "will_spend": False,
        "untimed_candidates": sum(1 for c in candidates if c.get("event", {}).get("time_seconds") is None),
    }


def run_review_pass(plan: dict, executor: Optional[Callable[[dict], Any]] = None) -> dict:
    """The review-pass code PATH. It is NOT wired to run automatically and makes NO
    provider call on its own. With no executor it executes nothing and reports that.
    An executor, if a caller ever injects one, is invoked per segment; wiring a real
    (paid) executor requires explicit approval and a real budget cap, neither of
    which is enabled here.
    """
    if executor is None:
        return {
            "status": "not_executed",
            "reason": "no executor wired; the review pass makes no provider call "
                      "without explicit wiring, a budget cap, and approval",
            "spent": 0,
            "results": [],
        }
    results = [executor(seg) for seg in plan.get("segments", [])]
    return {"status": "executed_with_injected_executor", "spent": 0, "results": results}


# ── 4. action-aware dedup (keeps distinct actions inside the 3s window) ───────
def _action_identity(ev: Any) -> tuple:
    et = (_field(ev, "event_type", "") or "").lower()
    made = _is_made_shot(ev) if et == "shot" else None
    player = _field(ev, "player") or _field(ev, "primary_player_jersey") or _field(ev, "ball_carrier_jersey")
    zone = _field(ev, "shot_zone")
    return (et, made, player, zone)


def _compatible_duplicate(a: tuple, b: tuple) -> bool:
    """True only when a and b could be the SAME action seen twice. Different event
    type, make-vs-miss, a different KNOWN player, or a different KNOWN zone each
    make them DISTINCT actions. A None on either side is 'unknown', not a mismatch,
    so a partial observation still merges into a fuller one. No invented IDs are
    used as proof."""
    if a[0] != b[0]:
        return False
    if a[1] is not None and b[1] is not None and a[1] != b[1]:
        return False
    if a[2] is not None and b[2] is not None and a[2] != b[2]:
        return False
    if a[3] is not None and b[3] is not None and a[3] != b[3]:
        return False
    return True


def dedup_basketball_actions(plays: list, window: float = BB_DEDUP_WINDOW) -> list:
    """Action-aware dedup for the basketball path. Merges only DUPLICATE
    OBSERVATIONS of one action (same identity evidence, within `window`) and KEEPS
    DISTINCT actions even when they fall inside the window (a putback right after a
    miss, a steal then a quick shot). The shipped time-only _deduplicate_plays
    cannot tell these apart; this can, using detected identity evidence only.

    Operates on detection dicts (pre-persist). Does not touch football behavior.
    """
    if not plays:
        return []
    ordered = sorted(plays, key=lambda p: (p.get("time_seconds") is None, p.get("time_seconds") or 0.0))
    kept: list = [ordered[0]]
    for play in ordered[1:]:
        merged = False
        pt = play.get("time_seconds")
        pid = _action_identity(play)
        # Only the most recent kept events can be a duplicate observation (time-ordered).
        for i in range(len(kept) - 1, -1, -1):
            k = kept[i]
            kt = k.get("time_seconds")
            if pt is not None and kt is not None and (pt - kt) >= window:
                break  # earlier kept events are out of the window
            if _compatible_duplicate(_action_identity(k), pid):
                # same action seen twice: keep the higher-confidence record, fill
                # any identity field it was missing from the other observation.
                if play.get("confidence", 0) > k.get("confidence", 0):
                    for f in ("player", "primary_player_jersey", "ball_carrier_jersey", "shot_zone"):
                        if play.get(f) is None and k.get(f) is not None:
                            play[f] = k[f]
                    kept[i] = play
                else:
                    for f in ("player", "primary_player_jersey", "ball_carrier_jersey", "shot_zone"):
                        if k.get(f) is None and play.get(f) is not None:
                            k[f] = play[f]
                merged = True
                break
        if not merged:
            kept.append(play)
    kept.sort(key=lambda p: (p.get("time_seconds") is None, p.get("time_seconds") or 0.0))
    return kept
