"""
Deterministic scoreboard score-delta reconciliation for basketball film.

The vision model reads the score bug per frame, but its make/miss and shot-type calls
are per-frame guesses. The scoreboard is ground truth: the total score only ticks UP on
a make, and by exactly how many points the shot was worth (1 = free throw, 2 or 3 = field
goal). This module turns the raw per-frame score reads the model reported into confirmed
scoring events, then rewrites shot outcomes from them, with NO model call and NO guessing.

Design choices that make this robust on single fixed-camera film:
- It reconciles on the TOTAL (home + away) score, so it never has to know which score on
  the bug belongs to the scouted team. A make raises the total by its point value no
  matter who scored, and the event maps to the most recent shot.
- A new total is accepted only when two consecutive readable frames agree on it, which
  debounces single-frame OCR misreads.
- Only monotonic increases of 1, 2, or 3 are accepted. Non-monotonic or larger jumps are
  discarded as unreliable rather than acted on.
- "Missed" is set only on POSITIVE evidence: the board is read again right after the shot
  and the total did not move. If the board is unreadable around a shot, the outcome is
  left exactly as the model left it (often null), never guessed. This honors the rule that
  defaulting to "Missed" is the worst error on this film.

Pure functions, stdlib only. Proving the logic needs no paid analysis run.
"""
from __future__ import annotations

MIN_READ_CONF = 0.5          # ignore shaky OCR reads below this confidence
WINDOW_BEFORE = 8.0          # a made basket posts on the bug 0-8s after the shot
MISS_AFTER_WINDOW = 12.0     # only confirm a miss if the board is read again this soon
AND_ONE_GAP = 15.0           # the bonus free throw after an and-1 lands within this window
SCOREBOARD_CONF = 0.95       # confidence stamped on a scoreboard-confirmed outcome
DEADBALL_FREEZE_S = 35.0     # clock frozen at one value this long = a prolonged dead ball

_THREE_ZONES = ("corner 3", "wing 3", "top of key 3", "half court")


def _clock_seconds(v):
    """Parse a game-clock string ('7:12', '13.5', '0:04.1') to seconds, or None."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("null", "none"):
        return None
    try:
        if ":" in s:
            parts = s.split(":")
            mm = int(parts[0])
            ss = float(parts[1])
            return mm * 60 + ss
        return float(s)
    except (ValueError, IndexError):
        return None


def _is_free_throw(p):
    st = (p.get("shot_type") or "").strip().lower()
    zone = (p.get("shot_zone") or "").strip().lower()
    return st == "free throw" or "free throw" in zone


def _clock_context(norm, t, freeze_s=DEADBALL_FREEZE_S, tol=0.6):
    """Classify the game-clock state around time t from the score reads. Returns one of
    'prolonged' (clock frozen at one value for >= freeze_s = timeout/dead ball),
    'stopped' (clock appears stopped but not that long), 'running', or 'unknown'.

    The clock VALUE being constant across consecutive reads is the reliable tell on wide
    single-cam film: a live shot happens with the clock counting down; a point that posts
    while the clock is frozen for a long stretch is a stoppage, not a live make."""
    cv = [r for r in norm if r.get("clock") is not None]
    if not cv:
        near = [r for r in norm if abs(r["t"] - t) <= 8.0 and r.get("clock_running") is not None]
        if not near:
            return "unknown"
        if all(r.get("clock_running") is False for r in near):
            return "stopped"
        if any(r.get("clock_running") is True for r in near):
            return "running"
        return "unknown"
    nearest = min(cv, key=lambda r: abs(r["t"] - t))
    if abs(nearest["t"] - t) > 12.0:
        return "unknown"
    val = nearest["clock"]
    i = cv.index(nearest)
    lo = hi = i
    while lo - 1 >= 0 and abs(cv[lo - 1]["clock"] - val) <= tol:
        lo -= 1
    while hi + 1 < len(cv) and abs(cv[hi + 1]["clock"] - val) <= tol:
        hi += 1
    dur = cv[hi]["t"] - cv[lo]["t"]
    if dur >= freeze_s:
        return "prolonged"
    stopped_near = any(abs(r["t"] - t) <= 6.0 and r.get("clock_running") is False for r in norm)
    if hi > lo or stopped_near:
        return "stopped"
    # a single read matches and the clock is changing on either side -> it's running
    return "running"


def _norm_reads(reads):
    """Normalize raw score reads to sorted {t, total, clock_running, conf}, dropping
    entries that are unreadable or below the confidence floor."""
    out = []
    for r in reads or []:
        if not isinstance(r, dict):
            continue
        try:
            t = float(r.get("t"))
        except (TypeError, ValueError):
            continue
        h, a = r.get("home"), r.get("away")
        if h is None or a is None:
            continue
        try:
            total = int(h) + int(a)
        except (TypeError, ValueError):
            continue
        try:
            conf = float(r.get("conf", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        if conf < MIN_READ_CONF:
            continue
        out.append({"t": t, "total": total,
                    "clock": _clock_seconds(r.get("clock")),
                    "clock_running": r.get("clock_running"), "conf": conf})
    out.sort(key=lambda x: x["t"])
    return out


def confirmed_totals(reads):
    """Collapse noisy per-frame totals into confirmed (t_first_seen, total) steps. A new
    total is accepted only once two consecutive kept reads agree on it, which debounces a
    single-frame OCR misread. The timestamp is the first frame the new value appeared."""
    norm = _norm_reads(reads)
    confirmed = []
    pending = None     # (value, t_first_seen)
    current = None
    for r in norm:
        v = r["total"]
        if current is not None and v == current:
            pending = None
            continue
        if pending and pending[0] == v:
            confirmed.append((pending[1], v))
            current = v
            pending = None
        else:
            pending = (v, r["t"])
    return confirmed


def scoring_events(confirmed):
    """From confirmed totals, emit a scoring event {t, points} for each monotonic increase
    of 1, 2, or 3. Decreases, zero, or jumps > 3 are skipped as unreliable (never acted on)."""
    events = []
    prev = None
    for t, total in confirmed:
        if prev is not None:
            d = total - prev
            if d in (1, 2, 3):
                events.append({"t": t, "points": d})
        prev = total
    return events


def _clock_stopped_near(norm, t, tol=3.0):
    """True if the nearest readable frame within `tol` seconds shows the clock stopped,
    False if running, None if there is no nearby read."""
    best = None
    for r in norm:
        dt = abs(r["t"] - t)
        if dt <= tol and (best is None or dt < best[0]):
            best = (dt, r.get("clock_running"))
    if best is None:
        return None
    cr = best[1]
    if cr is None:
        return None
    return cr is False


def _running_total_before(confirmed, t):
    val = None
    for ts, total in confirmed:
        if ts <= t:
            val = total
        else:
            break
    return val


def _stable_total_after(norm, t, window):
    """A total AFTER time t is 'stable' only if the first few reads in the window all agree
    (>= 2 reads). Returns that total, else None. Used to confirm a miss without acting on a
    single possibly-misread frame."""
    seen = [r["total"] for r in norm if t < r["t"] <= t + window]
    if len(seen) >= 2 and len(set(seen[:3])) == 1:
        return seen[0]
    return None


def _is_shot(p):
    return (p.get("event_type") or "") == "shot" and isinstance(p.get("time_seconds"), (int, float))


def plan_timeline_batches(frame_paths, cadence, bsz, max_calls):
    """Plan the dedicated scoreboard-only pass from the frames already extracted for
    detection. Keep roughly one frame per `cadence` seconds (so two consecutive kept
    reads can confirm a total via the debounce in confirmed_totals), split into batches
    of `bsz` frames, and if that exceeds `max_calls` thin the batches EVENLY so the whole
    game is still covered while the vision-call count stays hard-capped. `frame_paths` is
    a list of (path, timestamp). Returns (batches, picked_count).

    Pure + network-free so the sampling cadence and the call cap are unit-tested without
    extracting a single frame or making a model call."""
    picked, last_t = [], None
    for item in sorted(frame_paths, key=lambda x: x[1]):
        t = item[1]
        if last_t is None or (t - last_t) >= cadence:
            picked.append(item)
            last_t = t
    if not picked:
        return [], 0
    bsz = max(1, int(bsz))
    batches = [picked[i:i + bsz] for i in range(0, len(picked), bsz)]
    max_calls = max(1, int(max_calls))
    if len(batches) > max_calls:
        step = len(batches) / max_calls
        batches = [batches[int(i * step)] for i in range(max_calls)]
    return batches, len(picked)


def reconcile(plays, reads, *, has_scoreboard=True, enabled=True,
              suppress_deadball=True, freeze_s=DEADBALL_FREEZE_S):
    """Rewrite basketball shot outcomes from the scoreboard score-delta timeline.

    Returns (plays, stats). `plays` is mutated in place and also returned. When the film has
    no scoreboard or the feature is disabled, nothing changes. A corrected shot is stamped
    result_source='scoreboard' and result_verified=True so the UI and the learning loop can
    see it was locked to ground truth rather than guessed.

    Dead-ball suppression (suppress_deadball): wide single-cam film cannot support
    frame-accurate event tagging — the detector confabulates shots during stoppages
    (warmup shooting, inbounds). The scoreboard is the only reliable spine, so:
      A) a detected FIELD GOAL at a stopped clock is impossible (you cannot shoot a live
         field goal with the clock stopped) and is suppressed as a dead-ball phantom,
         unless a real +2/+3 aligns to it.
      B) a point that posts while the clock is frozen for a PROLONGED stretch (a timeout /
         extended dead ball) is reported as "point scored, play unclear" rather than a
         fabricated made shot stamped on a dead-ball frame.
    """
    stats = {"deltas_accepted": 0, "made_set": 0, "missed_set": 0,
             "ft_type_fixed": 0, "and_one": 0, "left_null": 0,
             "suppressed": 0, "unclear_points": 0}
    if not enabled or not has_scoreboard:
        return plays, stats

    norm = _norm_reads(reads)
    confirmed = confirmed_totals(reads)
    events = scoring_events(confirmed)
    stats["deltas_accepted"] = len(events)

    shots = sorted([p for p in plays if _is_shot(p)], key=lambda p: p["time_seconds"])

    # 1) Free-throw TYPE fix (independent of score): a shot from the free-throw line with a
    #    stopped clock is a free throw, never a layup/jumper. This alone kills the
    #    "free throw labeled layup" error even when the score is unreadable.
    for p in shots:
        zone = (p.get("shot_zone") or "").strip().lower()
        if "free throw" not in zone:
            continue
        if (p.get("shot_type") or "") == "Free Throw":
            continue
        stopped = _clock_stopped_near(norm, p["time_seconds"])
        st = (p.get("shot_type") or "")
        if stopped is True or st in ("Layup", "Floater", "Pull-Up Jumper", "Bank Shot", "Catch and Shoot", ""):
            p["shot_type"] = "Free Throw"
            stats["ft_type_fixed"] += 1

    # 2) Map each scoring event to the most recent unused shot 0-8s before it, and lock the
    #    outcome and point value from the score change.
    used = set()
    prev_event = None
    for ev in events:
        t, pts = ev["t"], ev["points"]
        cand = None
        for p in reversed(shots):
            if id(p) in used:
                continue
            ts = p["time_seconds"]
            if t - WINDOW_BEFORE <= ts <= t + 0.5:
                cand = p
                break
        if cand is None:
            # The board moved but no detected shot aligns — a real point we can't attribute
            # to a specific play. Keep the score fact; never invent a shot.
            stats["unclear_points"] += 1
            prev_event = ev
            continue
        # Rule B: the mapped shot sits inside a PROLONGED frozen-clock window (timeout /
        # extended dead ball). The detector's specific shot read there is unreliable, so
        # preserve the point but do NOT assert a made free throw/layup on a dead-ball frame.
        if suppress_deadball and _clock_context(norm, cand["time_seconds"], freeze_s) == "prolonged":
            used.add(id(cand))
            cand["result"] = None
            cand["shot_type"] = "Unclear"
            cand["points"] = pts
            cand["result_source"] = "scoreboard_unconfirmed_play"
            cand["play_unclear"] = True
            cand["confidence"] = min(float(cand.get("confidence") or 0), 0.4)
            cand["play_description"] = (
                f"Point scored (+{pts}) during a stopped-clock dead ball; the specific "
                f"play could not be confirmed on single-camera film.")
            stats["unclear_points"] += 1
            prev_event = ev
            continue
        used.add(id(cand))
        cand["result"] = "Made"
        cand["points"] = pts
        cand["result_source"] = "scoreboard"
        cand["result_verified"] = True
        cand["confidence"] = max(float(cand.get("confidence") or 0), SCOREBOARD_CONF)
        if pts == 1:
            cand["shot_type"] = "Free Throw"
            if "free throw" not in (cand.get("shot_zone") or "").lower():
                cand["shot_zone"] = "Free Throw Line"
        elif pts == 3:
            zone = (cand.get("shot_zone") or "").lower()
            if any(z in zone for z in _THREE_ZONES) or "3" in (cand.get("shot_type") or ""):
                cand["shot_type"] = "3-Pointer"
        stats["made_set"] += 1
        # and-1: a +1 shortly after a +2 is the bonus free throw. Flag it for the coach.
        if (prev_event and pts == 1 and prev_event["points"] == 2
                and 0 < (t - prev_event["t"]) <= AND_ONE_GAP):
            cand["and_one"] = True
            stats["and_one"] += 1
        prev_event = ev

    # 3) Remaining (unmapped) shots.
    for p in shots:
        if id(p) in used:
            continue
        ts = p["time_seconds"]
        # Rule A: a detected FIELD GOAL at a stopped clock with no supporting score change
        # is a dead-ball phantom (inbound, warmup shooting). You cannot shoot a live field
        # goal with the clock stopped — suppress it instead of calling it a make or a miss.
        if suppress_deadball and not _is_free_throw(p):
            ctx = _clock_context(norm, ts, freeze_s)
            if ctx in ("stopped", "prolonged"):
                p["result"] = None
                p["suppressed"] = True
                p["result_source"] = "dead_ball_suppressed"
                p["suppressed_reason"] = "field goal during a stopped clock (dead ball)"
                p["confidence"] = min(float(p.get("confidence") or 0), 0.3)
                stats["suppressed"] += 1
                continue
        # Misses: only on positive evidence — the board was read right after the shot and the
        # total did not move. Never a guess; an unreadable board leaves the shot untouched.
        before = _running_total_before(confirmed, ts)
        after = _stable_total_after(norm, ts, MISS_AFTER_WINDOW)
        if before is not None and after is not None and after == before:
            if p.get("result") != "Missed":
                p["result"] = "Missed"
                p["result_source"] = "scoreboard"
                p["result_verified"] = True
                stats["missed_set"] += 1
        elif p.get("result") is None:
            stats["left_null"] += 1

    return plays, stats
