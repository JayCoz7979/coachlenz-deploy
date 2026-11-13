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

_THREE_ZONES = ("corner 3", "wing 3", "top of key 3", "half court")


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


def reconcile(plays, reads, *, has_scoreboard=True, enabled=True):
    """Rewrite basketball shot outcomes from the scoreboard score-delta timeline.

    Returns (plays, stats). `plays` is mutated in place and also returned. When the film has
    no scoreboard or the feature is disabled, nothing changes. A corrected shot is stamped
    result_source='scoreboard' and result_verified=True so the UI and the learning loop can
    see it was locked to ground truth rather than guessed.
    """
    stats = {"deltas_accepted": 0, "made_set": 0, "missed_set": 0,
             "ft_type_fixed": 0, "and_one": 0, "left_null": 0}
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

    # 3) Misses: only on positive evidence — the board was read right after the shot and the
    #    total did not move. Never a guess; an unreadable board leaves the shot untouched.
    for p in shots:
        if id(p) in used:
            continue
        ts = p["time_seconds"]
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
