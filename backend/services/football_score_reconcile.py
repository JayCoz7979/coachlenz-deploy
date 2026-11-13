"""
Deterministic scoreboard score-delta reconciliation for FOOTBALL film.

The sister module to score_reconcile.py (basketball). The vision model reads the score
bug per frame and labels each play's result from a wide single-camera angle, but a
scoring play on that angle is easy to mislabel: a long run tagged "Touchdown" that was
actually stopped at the 2, a field goal or extra point whose outcome (good vs no-good)
the camera never shows cleanly, a real score on a snap the detector missed entirely.

The scoreboard is ground truth. In football the total (home + away) only ticks UP on a
score, and by exactly how many points:
    +6 = touchdown                      +1 = extra point (PAT) good
    +3 = field goal good                +2 = safety OR two-point conversion
    +7 = touchdown + PAT        (decomposes to 6 then 1)
    +8 = touchdown + two-point  (decomposes to 6 then 2)
This module turns the raw per-frame score reads the model reported into confirmed scoring
events, attributes each to the detected play it belongs to, and locks that play's result
from the score change, with NO model call and NO guessing.

Design choices that make this robust on single-camera film, mirroring the basketball module:
- It reconciles on the TOTAL score, so it never needs to know which number on the bug is
  the scouted team. A score raises the total by its point value no matter who scored, and
  the event maps to the most recent play.
- A new total is accepted only when two consecutive readable frames agree on it, which
  debounces a single-frame OCR misread.
- Only football-legal increases (1, 2, 3, 6, 7, 8) are accepted. Other jumps or decreases
  are discarded as unreliable rather than acted on. Compound 7 and 8 are decomposed into
  their component scores so the touchdown and the try that followed each map to their own
  snap.
- A point with no detected play after a strict then a widened window is SYNTHESIZED as a
  scoreboard-confirmed score of the correct value, with the scorer and detail left BLANK
  and flagged for review, rather than dropped or invented. The coach confirming that detail
  is exactly the signal the learning loop compounds.
- A miss (a field-goal or extra-point ATTEMPT whose score did not post) and a phantom
  touchdown (a play tagged "Touchdown" the board never credited) are corrected ONLY on
  POSITIVE evidence: the board is read again right after the play and the total did not
  move. If the board is unreadable around a play, the result is left exactly as the model
  left it, never guessed. Defaulting a kick to "Missed" or stripping a score on silence is
  the worst error on this film, so it never happens.

Unlike basketball, a stopped clock is NORMAL on a football score (the clock stops after
every score), so there is no dead-ball suppression here.

Pure functions, stdlib only. Proving the logic needs no paid analysis run.
"""
from __future__ import annotations

MIN_READ_CONF = 0.5          # ignore shaky OCR reads below this confidence
STRICT_BEFORE = 15.0         # a score posts on the bug 0-15s after the scoring snap
STRICT_AFTER = 2.0
RELAXED_BEFORE = 40.0        # second pass: the dedicated score read timestamps a delta at
RELAXED_AFTER = 5.0          #   the first frame the new total appeared, which can lag the
#                              scoring snap by a sampling gap. The widened pass reclaims a
#                              real scoring play only when it already LOOKS like a score
#                              (TD/made result, or a kicking down), so a wide window never
#                              crowns a random earlier snap a touchdown.
MISS_AFTER_WINDOW = 20.0     # only correct a kick to "Missed" if the board is read again
#                              this soon and did not move (positive evidence of no-good)
TWO_PT_GAP = 25.0            # a +2 within this window after a +6 is a two-point try; a +2
#                              with no recent touchdown is a safety
SCOREBOARD_CONF = 0.95       # confidence stamped on a scoreboard-confirmed outcome

ACCEPTED_DELTAS = (1, 2, 3, 6, 7, 8)

# play_type / st_unit values that mark a kicking (scoring-attempt) down.
_KICK_TYPES = ("field goal", "pat", "two-point", "two point", "extra point")


def _is_play(p):
    """A reconcilable football play: a dict with a numeric timestamp. Football plays carry
    no event_type at this stage (it is stamped 'play' only at persist), so we key off the
    real frame timestamp the detector assigned."""
    return isinstance(p, dict) and isinstance(p.get("time_seconds"), (int, float))


def _norm_reads(reads):
    """Normalize raw score reads to sorted {t, total, conf}, dropping entries that are
    unreadable or below the confidence floor. The clock is not needed for football
    reconciliation (a score legitimately stops the clock), so it is ignored."""
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
        out.append({"t": t, "total": total, "conf": conf})
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
    """From confirmed totals, emit a scoring event for each football-legal increase.

    Each event is {t, points, kind, order}:
      kind  one of 'touchdown', 'field_goal', 'pat', 'two_point', 'safety'
      order within a single board update, the chronological rank of the scoring action
            (0 = earliest). A compound +7/+8 is one board jump but two actions on film: the
            touchdown first (order 0) then the try (order 1). Mapping uses this so the try,
            which is closest to the board update, claims the most recent snap and the
            touchdown claims the snap before it.

    A standalone +2 is a two-point conversion when a touchdown posted within TWO_PT_GAP
    just before it, otherwise a safety. Non-legal jumps, zero, and decreases are skipped.
    """
    events = []
    prev = None
    prev_td_t = None
    for t, total in confirmed:
        if prev is not None:
            d = total - prev
            if d in ACCEPTED_DELTAS:
                if d == 6:
                    events.append({"t": t, "points": 6, "kind": "touchdown", "order": 0})
                    prev_td_t = t
                elif d == 3:
                    events.append({"t": t, "points": 3, "kind": "field_goal", "order": 0})
                elif d == 1:
                    events.append({"t": t, "points": 1, "kind": "pat", "order": 0,
                                   "require_kick": True})
                elif d == 2:
                    kind = ("two_point"
                            if prev_td_t is not None and 0 <= (t - prev_td_t) <= TWO_PT_GAP
                            else "safety")
                    events.append({"t": t, "points": 2, "kind": kind, "order": 0})
                elif d == 7:
                    events.append({"t": t, "points": 6, "kind": "touchdown", "order": 0})
                    events.append({"t": t, "points": 1, "kind": "pat", "order": 1,
                                   "require_kick": True})
                    prev_td_t = t
                elif d == 8:
                    events.append({"t": t, "points": 6, "kind": "touchdown", "order": 0})
                    events.append({"t": t, "points": 2, "kind": "two_point", "order": 1})
                    prev_td_t = t
        prev = total
    return events


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
    (>= 2 reads). Returns that total, else None. Used to confirm a no-good kick or a phantom
    touchdown on positive evidence, never on a single possibly-misread frame."""
    seen = [r["total"] for r in norm if t < r["t"] <= t + window]
    if len(seen) >= 2 and len(set(seen[:3])) == 1:
        return seen[0]
    return None


def _st_unit(p):
    return (p.get("st_unit") or "").strip().lower()


def _play_type(p):
    return (p.get("play_type") or "").strip().lower()


def _is_kick_attempt(p):
    """A field-goal, extra-point, or two-point ATTEMPT snap. These are the plays whose
    outcome the scoreboard can confirm or deny (good = total rises, no-good = total flat)."""
    pt, su = _play_type(p), _st_unit(p)
    if any(k in pt for k in _KICK_TYPES) or any(k in su for k in _KICK_TYPES):
        return True
    return bool(p.get("kick_result") or p.get("fg_distance_yds"))


def _scoring_affinity(p):
    """True if the detected play already looks like a score or a kicking down. The relaxed
    (wide-window) mapping pass only attaches a score to a play with this affinity, so a
    generous window can reclaim a real scoring snap the score read timestamped late without
    ever relabeling an ordinary earlier snap as a touchdown."""
    res = (p.get("result") or "").strip().lower()
    kr = (p.get("kick_result") or "").strip().lower()
    if res in ("touchdown", "made") or kr in ("made",):
        return True
    return _is_kick_attempt(p)


def _label_description(kind, pts):
    if kind == "touchdown":
        return f"Touchdown (+6) confirmed by the scoreboard."
    if kind == "field_goal":
        return f"Field goal good (+3) confirmed by the scoreboard."
    if kind == "pat":
        return f"Extra point good (+1) confirmed by the scoreboard."
    if kind == "two_point":
        return f"Two-point conversion good (+2) confirmed by the scoreboard."
    if kind == "safety":
        return (f"Safety (+2) confirmed by the scoreboard. A safety is scored by the "
                f"defense; confirm which unit was on the field.")
    return f"Score (+{pts}) confirmed by the scoreboard."


def _apply_score(p, kind, pts, *, relaxed, stats):
    """Lock a detected play's result from the confirmed score it was mapped to."""
    p["points"] = pts
    p["result_source"] = "scoreboard"
    p["result_verified"] = True
    p["scoring_play"] = True
    p["scoring_type"] = {
        "touchdown": "Touchdown", "field_goal": "Field Goal", "pat": "PAT",
        "two_point": "Two-Point Conversion", "safety": "Safety",
    }[kind]
    p["confidence"] = max(float(p.get("confidence") or 0), SCOREBOARD_CONF)
    if kind == "touchdown":
        p["result"] = "Touchdown"
    elif kind in ("field_goal", "pat", "two_point"):
        p["result"] = "Made"
    # 'safety' has no clean result enum value; the scoring_type + description carry it and
    # the detected result is left intact rather than forced into a wrong bucket.
    desc = _label_description(kind, pts)
    # A relaxed-window map or a safety/two-point (ambiguous scoring unit) still wants the
    # coach's eyes; a strict touchdown/field goal/PAT is board-definitive.
    if relaxed or kind in ("safety", "two_point"):
        p["needs_review"] = True
        desc += " Confirm the scorer and detail."
    p["play_description"] = desc
    if relaxed:
        stats["relaxed_mapped"] += 1
    stats[{
        "touchdown": "touchdowns_set", "field_goal": "field_goals_set", "pat": "pats_set",
        "two_point": "two_point_set", "safety": "safeties_set",
    }[kind]] += 1


def _synthesize_score(t, kind, pts):
    """Build a scoreboard-CONFIRMED scoring play for an event no detected play could be
    mapped to. The board objectively rose by `pts`, so a score of that value happened at
    time `t`; that is ground truth, not a per-frame guess. We stamp only what the scoreboard
    proves (the outcome and the point value) and deliberately leave the scorer, side, and
    detail BLANK and flagged for review rather than invent a snap that was never read. The
    coach confirming that detail is exactly the signal the learning loop compounds."""
    scoring_type = {
        "touchdown": "Touchdown", "field_goal": "Field Goal", "pat": "PAT",
        "two_point": "Two-Point Conversion", "safety": "Safety",
    }[kind]
    result = "Touchdown" if kind == "touchdown" else ("Made" if kind != "safety" else None)
    desc = (f"{_label_description(kind, pts)} The scoring play could not be identified on "
            f"single-camera film. Confirm to log who scored and how.")
    p = {
        "time_seconds": round(float(t), 2),
        "points": pts,
        "result_source": "scoreboard_synthesized",
        "result_verified": True,
        "synthesized": True,
        "scoring_play": True,
        "scoring_type": scoring_type,
        "needs_review": True,
        "confidence": SCOREBOARD_CONF,
        "play_description": desc,
    }
    if result is not None:
        p["result"] = result
    return p


def reconcile(plays, reads, *, has_scoreboard=True, enabled=True, synthesize=True):
    """Rewrite football play outcomes from the scoreboard score-delta timeline.

    Returns (plays, stats). `plays` is mutated in place and also returned (synthesized
    scores are appended). When the film has no scoreboard or the feature is disabled,
    nothing changes. A corrected play is stamped result_source='scoreboard' and
    result_verified=True so the UI and the learning loop can see it was locked to ground
    truth rather than guessed.
    """
    stats = {"deltas_accepted": 0, "touchdowns_set": 0, "field_goals_set": 0,
             "pats_set": 0, "two_point_set": 0, "safeties_set": 0,
             "missed_kicks_set": 0, "phantom_td_fixed": 0,
             "relaxed_mapped": 0, "synthesized": 0, "unclear_points": 0}
    if not enabled or not has_scoreboard:
        return plays, stats

    norm = _norm_reads(reads)
    confirmed = confirmed_totals(reads)
    events = scoring_events(confirmed)
    stats["deltas_accepted"] = len(events)

    plays_sorted = sorted([p for p in plays if _is_play(p)], key=lambda p: p["time_seconds"])

    # Attribute each scoring event to a detected play, then lock the result and point value.
    # Mapping runs in TWO passes, and within a single board update the later action (the
    # try after a touchdown) is mapped first so it claims the most recent snap:
    #   strict  [t-15, t+2]  — the scoring snap is almost always the snap just before the
    #                          board updates.
    #   relaxed [t-40, t+5]  — reclaim a real scoring snap the score read timestamped late,
    #                          but ONLY a play that already looks like a score.
    used = set()
    mapping = [[ev, None, False] for ev in events]   # [event, mapped_play, was_relaxed]
    # Map the later action within a board update first (order desc), earliest updates first.
    order = sorted(range(len(mapping)), key=lambda i: (mapping[i][0]["t"], -mapping[i][0]["order"]))

    def _try_map(before_w, after_w, require_affinity):
        n = 0
        for i in order:
            pair = mapping[i]
            if pair[1] is not None:
                continue
            ev = pair[0]
            t = ev["t"]
            for p in reversed(plays_sorted):
                if id(p) in used:
                    continue
                ts = p["time_seconds"]
                if t - before_w <= ts <= t + after_w:
                    # An extra point is always a kick, so it only maps to a kicking snap;
                    # if the kick snap was not detected it synthesizes rather than steal the
                    # touchdown snap it was compounded with.
                    if ev.get("require_kick") and not _is_kick_attempt(p):
                        continue
                    if require_affinity and not _scoring_affinity(p):
                        continue
                    used.add(id(p))
                    pair[1] = p
                    pair[2] = require_affinity
                    n += 1
                    break
        return n

    _try_map(STRICT_BEFORE, STRICT_AFTER, False)
    _try_map(RELAXED_BEFORE, RELAXED_AFTER, True)

    for ev, cand, was_relaxed in mapping:
        if cand is None:
            # The board rose but no detected play aligns, after both passes. The scoreboard
            # is ground truth that a score of this value happened, so synthesize it with the
            # scorer and detail left blank and flagged for review, rather than drop a real
            # score or invent a snap.
            if synthesize:
                plays.append(_synthesize_score(ev["t"], ev["kind"], ev["points"]))
                stats["synthesized"] += 1
            else:
                stats["unclear_points"] += 1
            continue
        _apply_score(cand, ev["kind"], ev["points"], relaxed=was_relaxed, stats=stats)

    # Remaining (unmapped) plays: correct only on POSITIVE evidence that the board was read
    # right after the play and did not move.
    for p in plays_sorted:
        if id(p) in used:
            continue
        ts = p["time_seconds"]
        before = _running_total_before(confirmed, ts)
        after = _stable_total_after(norm, ts, MISS_AFTER_WINDOW)
        board_flat = before is not None and after is not None and after == before
        if not board_flat:
            continue
        # A field-goal / extra-point / two-point attempt whose score never posted is no-good.
        if _is_kick_attempt(p):
            if p.get("result") != "Missed":
                p["result"] = "Missed"
                p["result_source"] = "scoreboard"
                p["result_verified"] = True
                p["scoring_play"] = False
                p["play_description"] = (
                    "Kick / try NO GOOD: the scoreboard did not move after this attempt.")
                stats["missed_kicks_set"] += 1
            continue
        # A play tagged a touchdown the board never credited was not a touchdown (stopped
        # short, called back, or a misread). Strip the score claim and flag it, but keep the
        # play as a gain rather than assert a specific yardage we cannot see.
        if (p.get("result") or "").strip().lower() == "touchdown":
            p["result"] = "Gain"
            p["scoring_play"] = False
            p["scoreboard_contradicted"] = True
            p["result_source"] = "scoreboard"
            p["result_verified"] = True
            p["needs_review"] = True
            p["play_description"] = (
                "Detected as a touchdown, but the scoreboard did not credit a score here, "
                "so it is logged as a gain. Confirm where the play ended.")
            stats["phantom_td_fixed"] += 1

    return plays, stats
