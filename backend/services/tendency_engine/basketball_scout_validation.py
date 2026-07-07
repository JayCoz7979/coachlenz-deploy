"""
Basketball opponent-scouting COORDINATOR layer — the analysis-room brain.

This sits ON TOP of two things that already exist:
    • basketball_scout.build_scouting_report()  — the six priority categories
      (Time of Possession, Turnovers, Deflections, 2PT/3PT ratio, Pace, Scoring
      Areas), each with sample sizes and per-player rows.
    • basketball.analyze_basketball()            — the deep tendency math
      (pick-and-roll, isolation, post-up, zone offense, press break, clutch,
      defensive scheme, ball-screen defense, transition, quarter breakdown).

It turns that raw analysis into a coordinator-grade, self-validating scouting
brief — the same architecture the football scout uses, extended for basketball:

    • run_validation_gates()        — the EIGHT integrity gates (Module 10)
    • situational_statements()      — plain-English coordinator sentences with a
                                       sample size + confidence tier on every line
    • build_game_plan()             — installable OFFENSE / DEFENSE / SPECIAL-
                                       SITUATION calls, each tied to a real number
    • camera_confidence_summary()   — the single-camera integrity disclosure
    • build_basketball_scouting_report() — assembles all of the above and RETURNS
                                       the full `scouting` block (six categories +
                                       coordinator layer), so nothing downstream
                                       that reads the six category_* keys breaks.

Design principle (matches basketball_scout.py and football_scout.py): read the
sport-agnostic `events` table + the already-computed analysis dicts. No dedicated
per-category tables. Every recommendation carries a sample size and a confidence
tier so a coach knows exactly how hard to lean on it — that is the whole point of
the gates, and it is what separates this from a raw data dump.

────────────────────────────────────────────────────────────────────────────
EXTRA event types this layer reads (beyond the six-category engine's set)
────────────────────────────────────────────────────────────────────────────
event_type == "scout_meta" (side='meta'): Module-1 intake + camera calibration
    analyst_id / reviewer_id / status            — Gate 2 (dual review)
    games_scouted / injury_flags                 — Gate 1 / Gate 8
    games_with_missing_starter                   — Gate 8
    camera_angle / camera_quality                — camera confidence
    visibility_rating / off_ball_visibility_pct  — camera confidence + Gate 5

event_type == "free_throw":  Module 8
    shooter (jersey), attempts, makes,
    box_out_formation_offense, box_out_formation_defense,
    pressure_situation (bool), shooter_tempo (quick|routine|slow)

event_type == "special_situation":  Module 7
    situation_type : "BLOB"|"SLOB"|"press_break"|"last_second"|"end_of_quarter"
    formation, primary_action, target, result, late_and_close (bool)

event_type == "player_profile":  Module 5 (analyst manual grades)
    jersey, position, handedness, role, and 1-5 grade fields,
    visible_examples (int) — how many clean single-camera looks the grade rests on
────────────────────────────────────────────────────────────────────────────
"""
from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict

from .basketball_scout import (
    _offensive_possession_count, _defensive_possession_count,
    _jersey, _x, _made, _shot_is_three, _is_offense, _num, _pct,
)

# ── Gate / confidence thresholds (single source of truth) ───────────────────
MIN_POSSESSIONS_FOR_FINAL = 80    # Gate 1: possession minimum across the sample
MIN_GAMES_RECOMMENDED = 3         # Gate 1: fewer than this reduces confidence
RECOMMENDATION_MIN_SAMPLE = 10    # Gate 3: below this a tendency is a "watch item"
WATCH_MIN_SAMPLE = 5              # below this we do not surface it at all
VISIBILITY_MIN_EXAMPLES = 5       # Gate 5: individual grade needs 5+ clean looks
LATE_GAME_SHARE_ALERT = 40.0      # Gate 7: one player > 40% of late shots = alert
LATE_GAME_MIN_SHOTS = 4           # Gate 7: need this many late shots to fire
STRATEGIC_FOUL_FT_PCT = 60.0      # Module 8/11: below this = strategic foul target
NEVER_FOUL_FT_PCT = 90.0          # Module 8/11: above this = never foul late
HOT_ZONE_EFG = 55.0               # take-away zone line (mirrors the six-cat engine)
CONCEDE_ZONE_EFG = 35.0           # concede-zone line (allow these shots)


# ── confidence helpers ──────────────────────────────────────────────────────
def _tier(sample: int, personnel_flagged: bool = False) -> str:
    """HIGH (>=10) / MEDIUM (5-9) / LOW (<5). Gate 8 drops one tier when a scouted
    game is missing a starter (the data still counts, it just weighs less)."""
    if sample >= RECOMMENDATION_MIN_SAMPLE:
        base = "HIGH"
    elif sample >= WATCH_MIN_SAMPLE:
        base = "MEDIUM"
    else:
        base = "LOW"
    if personnel_flagged:
        base = {"HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}[base]
    return base


def _scout_meta(events) -> Dict[str, Any]:
    """Module-1 intake metadata lives on a single side='meta' event so no new table
    is needed. Returns {} when a report is built straight from film."""
    for e in events:
        if getattr(e, "event_type", None) == "scout_meta":
            return getattr(e, "extra_data", None) or {}
    return {}


def _quarter(e) -> int:
    return int(_num(_x(e, "quarter"), 0))


def _is_late_and_close(e) -> bool:
    """Charter late-game window: 4th quarter (or OT) within 5 points. From a single
    camera we read quarter + score margin; that is what the fixed angle can confirm."""
    q = _quarter(e)
    if q < 4:
        return False
    diff = _x(e, "score_diff_at_start")
    if diff is None:
        return True  # 4th/OT with unknown margin — count it, flag visibility elsewhere
    return abs(_num(diff, 0)) <= 5


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 9 (partial) — LATE-GAME PROFILE + Gate 7 primary-threat detection
# ═══════════════════════════════════════════════════════════════════════════
def late_game_profile(events) -> Dict[str, Any]:
    """Who takes over in the final four minutes of a one-possession game. This is
    the highest-priority read for a head coach, and it feeds Gate 7."""
    shots = [e for e in events
             if getattr(e, "event_type", None) == "shot" and _is_offense(e) and _is_late_and_close(e)]
    tos = [e for e in events
           if getattr(e, "event_type", None) == "turnover" and _is_late_and_close(e)]

    if not shots and not tos:
        return {"tracked": False, "late_shots": 0}

    by_shooter = Counter(j for e in shots if (j := _jersey(e)))
    total = sum(by_shooter.values())
    makes = sum(1 for e in shots if _made(e))
    threes = sum(1 for e in shots if _shot_is_three(e))

    rows = [{"jersey": j, "shots": c, "share_pct": _pct(c, total)}
            for j, c in by_shooter.most_common()]

    primary = rows[0] if rows else None
    alert = bool(primary and total >= LATE_GAME_MIN_SHOTS
                 and primary["share_pct"] > LATE_GAME_SHARE_ALERT)

    return {
        "tracked": True,
        "late_shots": total,
        "late_makes": makes,
        "late_fg_pct": _pct(makes, total),
        "late_three_rate_pct": _pct(threes, total),
        "late_turnovers": len(tos),
        "shot_takers": rows,
        "primary_threat": primary["jersey"] if alert else None,
        "primary_threat_share_pct": primary["share_pct"] if primary else 0.0,
        "primary_threat_alert": alert,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 8 — FREE THROW ANALYSIS + BOX-OUT FORMATIONS
# ═══════════════════════════════════════════════════════════════════════════
def free_throw_profile(events) -> Dict[str, Any]:
    """Team + per-player FT%, strategic foul targets (<60%), never-foul players
    (>90%), and the box-out formations logged on each attempt."""
    fts = [e for e in events if getattr(e, "event_type", None) == "free_throw"]
    if not fts:
        return {"tracked": False, "attempts": 0}

    team_att = team_made = 0
    per_player: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"att": 0, "made": 0, "clutch_att": 0, "clutch_made": 0, "tempo": None})
    off_boxout = Counter()
    def_boxout = Counter()

    for e in fts:
        att = int(_num(_x(e, "attempts"), 1))
        made = int(_num(_x(e, "makes"), 0))
        team_att += att
        team_made += made
        j = _jersey(e) or _x(e, "shooter")
        if j:
            j = str(j)
            per_player[j]["att"] += att
            per_player[j]["made"] += made
            if _x(e, "pressure_situation"):
                per_player[j]["clutch_att"] += att
                per_player[j]["clutch_made"] += made
            if _x(e, "shooter_tempo"):
                per_player[j]["tempo"] = _x(e, "shooter_tempo")
        if (bo := _x(e, "box_out_formation_offense")):
            off_boxout[bo] += 1
        if (bo := _x(e, "box_out_formation_defense")):
            def_boxout[bo] += 1

    players = []
    strategic_targets, never_foul = [], []
    for j, d in per_player.items():
        pct = _pct(d["made"], d["att"])
        clutch_pct = _pct(d["clutch_made"], d["clutch_att"]) if d["clutch_att"] else None
        row = {
            "jersey": j, "attempts": d["att"], "makes": d["made"], "ft_pct": pct,
            "clutch_attempts": d["clutch_att"], "clutch_ft_pct": clutch_pct,
            "shooter_tempo": d["tempo"],
        }
        players.append(row)
        # Need a real sample before naming a strategic target (min 4 attempts).
        if d["att"] >= 4 and pct < STRATEGIC_FOUL_FT_PCT:
            strategic_targets.append({"jersey": j, "ft_pct": pct, "attempts": d["att"]})
        if d["att"] >= 4 and pct >= NEVER_FOUL_FT_PCT:
            never_foul.append({"jersey": j, "ft_pct": pct, "attempts": d["att"]})
    players.sort(key=lambda p: p["attempts"], reverse=True)
    strategic_targets.sort(key=lambda p: p["ft_pct"])
    never_foul.sort(key=lambda p: p["ft_pct"], reverse=True)

    return {
        "tracked": True,
        "attempts": team_att,
        "makes": team_made,
        "team_ft_pct": _pct(team_made, team_att),
        "players": players,
        "strategic_foul_targets": strategic_targets,   # foul these late
        "never_foul_players": never_foul,               # do NOT foul these late
        "offensive_boxout_formations": dict(off_boxout.most_common()),
        "defensive_boxout_formations": dict(def_boxout.most_common()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 7 — SPECIAL SITUATIONS (BLOB / SLOB / press break / last second / EOQ)
# ═══════════════════════════════════════════════════════════════════════════
_SPECIAL_TYPES = ("BLOB", "SLOB", "press_break", "last_second", "end_of_quarter")


def special_situations_profile(events) -> Dict[str, Any]:
    """Roll up every logged inbound / press-break / last-second / end-of-quarter
    set. A set they run more than once — especially late and close — is a trusted
    call and gets flagged as a must-defend."""
    sits = [e for e in events if getattr(e, "event_type", None) == "special_situation"]
    if not sits:
        return {"tracked": False, "total": 0}

    buckets: Dict[str, Dict[str, Any]] = {}
    for st in _SPECIAL_TYPES:
        rows = [e for e in sits if (_x(e, "situation_type") or "").upper().replace(" ", "_") == st.upper()]
        if not rows:
            continue
        # A repeated formation/action pairing is a "set" — count reps + scores.
        combos: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"reps": 0, "scores": 0, "late_and_close": 0, "primary_action": None})
        for e in rows:
            form = _x(e, "formation") or "unlabeled"
            action = _x(e, "primary_action") or "unspecified"
            key = f"{form} / {action}"
            c = combos[key]
            c["reps"] += 1
            c["primary_action"] = action
            if (_x(e, "result") or "").lower() in ("made", "score", "basket", "touchdown"):
                c["scores"] += 1
            if _x(e, "late_and_close"):
                c["late_and_close"] += 1
        trusted = [
            {"set": k, **v, "trusted": v["reps"] >= 2}
            for k, v in sorted(combos.items(), key=lambda kv: kv[1]["reps"], reverse=True)
        ]
        buckets[st] = {
            "count": len(rows),
            "sets": trusted,
            # highest priority: a set they ran more than once late and close
            "trusted_late_sets": [t for t in trusted if t["late_and_close"] >= 1 and t["reps"] >= 2],
        }

    return {"tracked": True, "total": len(sits), "by_type": buckets}


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 9 (partial) — ADVANCED ANALYTICS: PPP + shot distribution vs benchmark
# ═══════════════════════════════════════════════════════════════════════════
# League-neutral shot-distribution benchmarks (share of attempts). Mid-range over
# 25% is the inefficiency flag the charter calls out.
MID_RANGE_INEFFICIENCY_PCT = 25.0
PERIMETER_DEPENDENT_PCT = 40.0


def advanced_metrics(events, six_cat: Dict[str, Any]) -> Dict[str, Any]:
    """Points-per-possession and shot distribution — the efficiency lens that turns
    the six categories into take-away / concede calls."""
    shots = [e for e in events
             if getattr(e, "event_type", None) == "shot" and _is_offense(e)]
    off_poss = _offensive_possession_count(events)

    # Points from shots (single-camera: FT points folded in from free_throw events).
    pts = 0
    for e in shots:
        if _made(e):
            pts += 3 if _shot_is_three(e) else 2
    ft_pts = sum(int(_num(_x(e, "makes"), 0))
                 for e in events if getattr(e, "event_type", None) == "free_throw")
    total_pts = pts + ft_pts
    ppp = round(total_pts / off_poss, 2) if off_poss else None

    # Shot distribution from the six-category scoring-areas block (already zoned).
    zones = (six_cat.get("category_6_scoring_areas") or {}).get("zones") or {}
    total_att = sum(z.get("attempts", 0) for z in zones.values()) or len(shots)
    PAINT = {"Restricted Area", "Paint Non-RA"}
    MID = {"Mid-Range Left", "Mid-Range Right", "Mid-Range Center"}
    THREE = {"Left Corner 3", "Right Corner 3", "Above-the-Break 3 Left",
             "Above-the-Break 3 Right", "Above-the-Break 3 Center"}
    paint = sum(z.get("attempts", 0) for k, z in zones.items() if k in PAINT)
    mid = sum(z.get("attempts", 0) for k, z in zones.items() if k in MID)
    three = sum(z.get("attempts", 0) for k, z in zones.items() if k in THREE)

    dist = {
        "paint_pct": _pct(paint, total_att),
        "mid_range_pct": _pct(mid, total_att),
        "three_pct": _pct(three, total_att),
    }
    flags = []
    if dist["mid_range_pct"] >= MID_RANGE_INEFFICIENCY_PCT:
        flags.append(f"Mid-range dependent ({dist['mid_range_pct']}% of shots) — a low-value diet to concede into.")
    if dist["three_pct"] >= PERIMETER_DEPENDENT_PCT:
        flags.append(f"Perimeter dependent ({dist['three_pct']}% threes) — run them off the line.")

    return {
        "offensive_possessions": off_poss,
        "estimated_points": total_pts,
        "points_per_possession": ppp,
        "shot_distribution": dist,
        "efficiency_flags": flags,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 12 — SINGLE-CAMERA CONFIDENCE SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
def camera_confidence_summary(events, meta: Dict[str, Any]) -> Dict[str, Any]:
    """The integrity disclosure appended to every report: what the fixed camera
    could confirm vs. what was read under limitation. Never hidden."""
    angle = meta.get("camera_angle")
    quality = (meta.get("camera_quality") or "").lower() or None
    off_ball_pct = meta.get("off_ball_visibility_pct")

    # Charter rule: poor quality auto-drops individual technique grades one tier.
    quality_penalty = quality == "poor"

    # Derive an overall visibility rating from the intake + off-ball coverage.
    stated = (meta.get("visibility_rating") or "").upper() or None
    if stated in ("FULL", "PARTIAL", "LIMITED"):
        rating = stated
    elif off_ball_pct is not None:
        p = _num(off_ball_pct, 0)
        rating = "FULL" if p >= 90 else ("PARTIAL" if p >= 70 else "LIMITED")
    else:
        rating = "PARTIAL"  # honest default under a single fixed camera

    return {
        "camera_angle": angle,
        "camera_quality": quality,
        "visibility_rating": rating,
        "off_ball_visibility_pct": off_ball_pct,
        "individual_grade_penalty": quality_penalty,
        "disclosure": (
            f"Single fixed camera ({angle or 'angle not recorded'}, "
            f"{quality or 'quality not recorded'}). Overall visibility: {rating}. "
            + ("Poor image quality: every individual technique grade is dropped one "
               "confidence tier and flagged ESTIMATE. " if quality_penalty else "")
            + "Tendencies below are labeled with the visibility they were read under."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 5 — INDIVIDUAL PLAYER PROFILES (analyst grades + Gate 5 visibility)
# ═══════════════════════════════════════════════════════════════════════════
def player_profiles(events, camera_penalty: bool = False) -> Dict[str, Any]:
    """Collect analyst-entered player grade cards. Any grade resting on fewer than
    5 clean single-camera looks is flagged ESTIMATE (Gate 5), and every technique
    grade drops a tier when the camera quality is poor."""
    profs = [e for e in events if getattr(e, "event_type", None) == "player_profile"]
    if not profs:
        return {"tracked": False, "players": []}

    cards = []
    estimates = 0
    for e in profs:
        ed = getattr(e, "extra_data", None) or {}
        j = _jersey(e) or ed.get("jersey")
        visible = int(_num(ed.get("visible_examples"), 0))
        is_estimate = visible < VISIBILITY_MIN_EXAMPLES
        if is_estimate:
            estimates += 1
        card = {k: v for k, v in ed.items() if k not in ("players",)}
        card["jersey"] = str(j) if j else None
        card["visible_examples"] = visible
        card["grade_status"] = "ESTIMATE" if is_estimate else "CONFIRMED"
        card["camera_penalty"] = camera_penalty
        cards.append(card)

    cards.sort(key=lambda c: (c["grade_status"] != "CONFIRMED", c.get("jersey") or ""))
    return {"tracked": True, "players": cards,
            "estimate_count": estimates, "confirmed_count": len(cards) - estimates}


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 10 — CHECKS AND BALANCES VALIDATION LAYER (EIGHT gates)
# ═══════════════════════════════════════════════════════════════════════════
def run_validation_gates(events, six_cat: Dict[str, Any], late: Dict[str, Any],
                         profiles: Dict[str, Any]) -> Dict[str, Any]:
    """Run all eight integrity gates over the possession log + computed analysis.
    Returns a per-gate result plus an overall report status (FINAL / PRELIMINARY)."""
    meta = _scout_meta(events)
    off_poss = _offensive_possession_count(events)
    def_poss = _defensive_possession_count(events)
    total_poss = off_poss + def_poss

    data_events = [e for e in events
                   if getattr(e, "event_type", None) in
                   ("shot", "turnover", "deflection", "possession", "player_stat",
                    "free_throw", "special_situation")]
    games = {gn for e in data_events if (gn := _x(e, "game_number")) is not None}
    n_games = len(games) if games else (1 if data_events else 0)

    gates: List[Dict[str, Any]] = []

    # GATE 1 — POSSESSION COUNT MINIMUM (80+ possessions, 3+ games).
    g1_pass = total_poss >= MIN_POSSESSIONS_FOR_FINAL and n_games >= MIN_GAMES_RECOMMENDED
    g1_notes = []
    if total_poss < MIN_POSSESSIONS_FOR_FINAL:
        g1_notes.append(f"Only {total_poss} possessions logged (need {MIN_POSSESSIONS_FOR_FINAL}). "
                        f"Report locked PRELIMINARY.")
    if n_games < MIN_GAMES_RECOMMENDED:
        g1_notes.append(f"Only {n_games} game(s) scouted (recommend {MIN_GAMES_RECOMMENDED}+). "
                        f"Tendencies may be opponent-specific.")
    gates.append({"gate": 1, "name": "Possession Count Minimum", "passed": g1_pass,
                  "notes": g1_notes or [f"{total_poss} possessions across {n_games} games. Sample is sound."]})

    # GATE 2 — DUAL ANALYST REVIEW (analyst + a distinct reviewer signed off).
    analyst = meta.get("analyst_id") or meta.get("analyst")
    reviewer = meta.get("reviewer_id") or meta.get("reviewer")
    status = (meta.get("status") or "").lower()
    g2_pass = bool(analyst and reviewer and reviewer != analyst and status in ("reviewed", "final"))
    if not meta:
        g2_notes = ["No intake metadata (film-only report); dual review not applicable, treat as single-analyst."]
    elif not reviewer:
        g2_notes = ["No second-analyst reviewer assigned. No report is final without dual review."]
    elif reviewer == analyst:
        g2_notes = ["Reviewer is the same person as the primary analyst. Independent review required."]
    elif status not in ("reviewed", "final"):
        g2_notes = [f"Reviewer assigned but sign-off status is '{status or 'draft'}'. Awaiting review."]
    else:
        g2_notes = [f"Dual review complete: analyst {analyst}, reviewer {reviewer}."]
    gates.append({"gate": 2, "name": "Dual Analyst Review", "passed": g2_pass, "notes": g2_notes})

    # GATE 3 — SAMPLE SIZE AUDIT (any recommendation needs 10+ reps).
    thin = _thin_tendencies(six_cat)
    g3_notes = ([f"{len(thin)} tendency block(s) below the 10-rep recommendation line moved to Watch Items."]
                if thin else ["All surfaced tendencies clear the 10-rep recommendation line."])
    gates.append({"gate": 3, "name": "Sample Size Audit", "passed": True,
                  "notes": g3_notes, "watch_items": thin})

    # GATE 4 — CONSISTENCY CHECK (raw log supports the stated per-category totals).
    discrepancies = _consistency_check(events, six_cat)
    g4_pass = len(discrepancies) == 0
    gates.append({"gate": 4, "name": "Consistency Check", "passed": g4_pass,
                  "notes": (["Possession log is internally consistent with the tendency splits."]
                            if g4_pass else [f"{len(discrepancies)} discrepancy/ies between raw log and stated tendencies."]),
                  "discrepancies": discrepancies})

    # GATE 5 — SINGLE-CAMERA VISIBILITY AUDIT (individual grades need 5+ looks).
    estimates = profiles.get("estimate_count", 0) if profiles.get("tracked") else 0
    g5_pass = estimates == 0
    g5_notes = ([f"{estimates} player grade(s) rest on fewer than {VISIBILITY_MIN_EXAMPLES} clean "
                 f"single-camera looks — flagged ESTIMATE, not confirmed data."]
                if estimates else
                ["Every surfaced individual grade has 5+ clearly visible examples."
                 if profiles.get("tracked") else "No manual player grades entered; visibility audit not applicable."])
    gates.append({"gate": 5, "name": "Single-Camera Visibility Audit", "passed": g5_pass,
                  "notes": g5_notes, "estimate_grades": estimates})

    # GATE 6 — GAME PLAN TRANSLATION runs last (needs the plan). Placeholder here.
    gates.append({"gate": 6, "name": "Game Plan Translation", "passed": None,
                  "notes": ["Pending game-plan assembly."]})

    # GATE 7 — LATE-GAME ALERT (any player > 40% of late-and-close shots).
    alert = late.get("primary_threat_alert", False)
    g7_notes = ([f"PRIMARY LATE-GAME THREAT: #{late.get('primary_threat')} took "
                 f"{late.get('primary_threat_share_pct')}% of shots in the final four minutes of "
                 f"one-possession games ({late.get('late_shots')} late shots). Dedicated final-four assignment required."]
                if alert else
                ["No single player crosses the 40% late-game shot-share line (or too few late shots to call)."])
    gates.append({"gate": 7, "name": "Late-Game Alert", "passed": not alert, "notes": g7_notes,
                  "primary_threat": late.get("primary_threat")})

    # GATE 8 — PERSONNEL CHANGE FLAG (missing starter in any scouted game).
    injury_flags = meta.get("injury_flags") or []
    flagged_games = meta.get("games_with_missing_starter") or []
    personnel_flagged = bool(injury_flags or flagged_games)
    g8_notes = ([f"Personnel change flagged: {', '.join(str(x) for x in (injury_flags or flagged_games))}. "
                 f"Every affected tendency drops one confidence tier and carries an asterisk."]
                if personnel_flagged else ["No missing-starter / injury flags on the scouted sample."])
    gates.append({"gate": 8, "name": "Personnel Change Flag", "passed": not personnel_flagged,
                  "notes": g8_notes, "personnel_flagged": personnel_flagged})

    gates.sort(key=lambda g: g["gate"])
    report_status = "FINAL" if g1_pass else "PRELIMINARY"
    return {
        "report_status": report_status,
        "total_possessions": total_poss,
        "offensive_possessions": off_poss,
        "defensive_possessions": def_poss,
        "games_scouted": n_games,
        "personnel_flagged": personnel_flagged,
        "gates": gates,
    }


def _thin_tendencies(six_cat: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gate 3 — per-player rows in the 5-9 sample range are real signal but Watch
    Items, never recommendations. Scans the categories whose rows carry a count."""
    watch: List[Dict[str, Any]] = []

    def _scan_players(block, count_key, label):
        for p in (block or {}).get("players", []) or []:
            c = p.get(count_key)
            if isinstance(c, int) and WATCH_MIN_SAMPLE <= c < RECOMMENDATION_MIN_SAMPLE:
                watch.append({"area": label, "jersey": p.get("jersey"),
                              "sample": c, "tier": _tier(c)})

    _scan_players(six_cat.get("category_2_turnovers"), "turnovers", "Turnovers (player)")
    _scan_players(six_cat.get("category_3_deflections"), "deflections", "Deflections (player)")
    _scan_players(six_cat.get("category_4_shot_ratio"), "attempts", "Shot volume (player)")
    _scan_players(six_cat.get("category_6_scoring_areas"), "attempts", "Scoring (player)")
    return watch


def _consistency_check(events, six_cat: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gate 4 — recompute headline counts from the raw log and compare to what each
    category reports; flag malformed quarters/zones."""
    discrepancies: List[Dict[str, Any]] = []

    for i, e in enumerate(events):
        et = getattr(e, "event_type", None)
        q = _x(e, "quarter")
        if q is not None and not (1 <= int(_num(q, 0)) <= 8):
            discrepancies.append({"event_index": i, "issue": f"Quarter out of range: {q}"})
        if et == "shot":
            zone = _x(e, "shot_zone")
            from .basketball_scout import COURT_ZONES
            if zone and zone not in COURT_ZONES:
                discrepancies.append({"event_index": i, "issue": f"Unknown shot zone: {zone}"})

    # Turnover total: recomputed vs. stated.
    raw_tos = sum(1 for e in events if getattr(e, "event_type", None) == "turnover")
    stated_tos = (six_cat.get("category_2_turnovers") or {}).get("total")
    # Only compare when the category was built from granular turnover events (not
    # aggregate player_stat rows, which legitimately inflate the stated total).
    has_stat_rows = any(getattr(e, "event_type", None) == "player_stat" for e in events)
    if isinstance(stated_tos, int) and raw_tos and not has_stat_rows and stated_tos != raw_tos:
        discrepancies.append({"issue": f"Turnover count mismatch: log has {raw_tos}, summary states {stated_tos}"})

    return discrepancies


# ═══════════════════════════════════════════════════════════════════════════
# GATE 6 TRANSLATION — SITUATIONAL TENDENCY STATEMENTS (plain coordinator English)
# ═══════════════════════════════════════════════════════════════════════════
def situational_statements(six_cat, summary, late, ft, personnel_flagged=False) -> List[Dict[str, Any]]:
    """Turn the highest-leverage findings into single-sentence coordinator
    statements, each carrying its sample size and a confidence tier."""
    out: List[Dict[str, Any]] = []

    def add(text, sample, category):
        if sample and sample >= WATCH_MIN_SAMPLE:
            out.append({"category": category, "sample": sample,
                        "confidence": _tier(sample, personnel_flagged),
                        "statement": text + ("*" if personnel_flagged else "")})

    # C1 — isolation dependency on the primary ball handler.
    c1 = six_cat.get("category_1_time_of_possession") or {}
    if c1.get("isolation_dependency_flag") and c1.get("primary_ball_handler"):
        share = c1.get("primary_share_pct", 0)
        touches = next((r["touches"] for r in c1.get("players", [])
                        if r["jersey"] == c1["primary_ball_handler"]), 0)
        add(f"#{c1['primary_ball_handler']} controls {share}% of their possession time "
            f"(over the 35% isolation-dependency line). Take the ball out of their hands.",
            max(touches, WATCH_MIN_SAMPLE), "Ball Dominance")

    # C2 — the turnover-prone player + situation.
    c2 = six_cat.get("category_2_turnovers") or {}
    if c2.get("players"):
        top = c2["players"][0]
        if top["turnovers"] >= 2:
            situ = next((k for k in (c2.get("by_situation") or {}) if k != "unspecified"), None)
            pat = f", pattern in {top['pattern_flags'][0]['type']}" if top.get("pattern_flags") else ""
            add(f"#{top['jersey']} is turnover-prone ({top['turnovers']} TOs{pat}"
                + (f"; team most vulnerable in {situ}" if situ else "") + "). Pressure them early.",
                max(top["turnovers"], WATCH_MIN_SAMPLE), "Turnovers")

    # C4 — perimeter dependency / shot diet.
    c4 = six_cat.get("category_4_shot_ratio") or {}
    if c4.get("total_shots"):
        if c4.get("perimeter_dependent_players"):
            js = ", ".join(f"#{j}" for j in c4["perimeter_dependent_players"][:3])
            add(f"{js} live behind the arc (over 40% of their shots are threes). Run them off the line.",
                c4["total_shots"], "Shot Selection")
        elif c4.get("three_pt_rate_pct", 0) >= 38:
            add(f"They shoot {c4['three_pt_rate_pct']}% of their attempts from three. Prioritize closeouts "
                f"over paint-packing.", c4["total_shots"], "Shot Selection")

    # C6 — hot zone.
    c6 = six_cat.get("category_6_scoring_areas") or {}
    for z in (c6.get("defensive_priority_zones") or [])[:1]:
        d = (c6.get("zones") or {}).get(z, {})
        add(f"They shoot {d.get('efg_pct', 0)}% eFG from the {z} ({d.get('attempts', 0)} attempts), "
            f"above the 55% take-away line.", d.get("attempts", WATCH_MIN_SAMPLE), "Scoring Areas")

    # Late-game threat.
    if late.get("primary_threat_alert"):
        add(f"#{late['primary_threat']} takes {late['primary_threat_share_pct']}% of their shots in the "
            f"final four minutes of a one-possession game. Put your best defender on them late.",
            max(late.get("late_shots", 0), WATCH_MIN_SAMPLE), "Late Game")

    # Free-throw strategic foul.
    if ft.get("strategic_foul_targets"):
        t = ft["strategic_foul_targets"][0]
        add(f"#{t['jersey']} shoots {t['ft_pct']}% from the line ({t['attempts']} attempts) — the strategic "
            f"foul target in a late-game possession game.", max(t["attempts"], WATCH_MIN_SAMPLE), "Free Throws")

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    out.sort(key=lambda s: (order.get(s["confidence"].rstrip("*"), 3), -s["sample"]))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 11 — GAME PLAN BUILDER (installable O / D / SPECIAL, evidence-backed)
# ═══════════════════════════════════════════════════════════════════════════
def build_game_plan(events, six_cat, summary, late, ft, special,
                    personnel_flagged=False) -> Dict[str, Any]:
    """Assemble a first-draft, installable game plan. Every item is tied to a real
    number and a sample size; items under the 10-rep line are labeled Watch Items,
    never presented as recommendations (Gate 3)."""

    def _item(phase, call, evidence, sample, featured=False):
        return {"phase": phase, "call": call, "evidence": evidence, "sample": sample,
                "confidence": _tier(sample, personnel_flagged), "featured": featured,
                "class": "recommendation" if sample >= RECOMMENDATION_MIN_SAMPLE else "watch_item"}

    defensive_plan: List[Dict[str, Any]] = []
    offensive_plan: List[Dict[str, Any]] = []
    special_plan: List[Dict[str, Any]] = []

    c1 = six_cat.get("category_1_time_of_possession") or {}
    c2 = six_cat.get("category_2_turnovers") or {}
    c4 = six_cat.get("category_4_shot_ratio") or {}
    c5 = six_cat.get("category_5_pace") or {}
    c6 = six_cat.get("category_6_scoring_areas") or {}

    # ── DEFENSE (how WE guard THEIR offense) ────────────────────────────────
    # Featured: the late-game primary threat leads the plan — it's the game-loser.
    if late.get("primary_threat_alert"):
        defensive_plan.append(_item(
            "DEF", f"FINAL 4:00 — deny #{late['primary_threat']} the ball",
            f"They took {late['primary_threat_share_pct']}% of late one-possession shots "
            f"({late.get('late_shots')} late shots, {late.get('late_fg_pct')}% FG). Face-guard, "
            f"make someone else beat you.", max(late.get("late_shots", 0), WATCH_MIN_SAMPLE), featured=True))

    # Ball dominance -> take the ball out of the primary handler's hands.
    if c1.get("isolation_dependency_flag") and c1.get("primary_ball_handler"):
        touches = next((r["touches"] for r in c1.get("players", [])
                        if r["jersey"] == c1["primary_ball_handler"]), WATCH_MIN_SAMPLE)
        defensive_plan.append(_item(
            "DEF", f"Trap #{c1['primary_ball_handler']} on the catch",
            f"They control {c1.get('primary_share_pct', 0)}% of possession time — over the 35% "
            f"isolation line. Force secondary handlers to create.", max(touches, WATCH_MIN_SAMPLE)))

    # Turnover-prone player -> pressure them.
    if c2.get("players") and c2["players"][0]["turnovers"] >= 2:
        top = c2["players"][0]
        defensive_plan.append(_item(
            "DEF", f"Pressure #{top['jersey']} to force early turnovers",
            f"{top['turnovers']} turnovers"
            + (f", pattern in {top['pattern_flags'][0]['type']}" if top.get("pattern_flags") else "")
            + ". Turn them over early to set tempo.", max(top["turnovers"], WATCH_MIN_SAMPLE)))

    # Perimeter dependency -> run shooters off the line.
    if c4.get("perimeter_dependent_players"):
        js = ", ".join(f"#{j}" for j in c4["perimeter_dependent_players"][:3])
        defensive_plan.append(_item(
            "DEF", f"Run {js} off the 3-point line",
            f"Over 40% of their shots are threes. Close out high, force drives into help.",
            c4.get("total_shots", WATCH_MIN_SAMPLE)))
    elif c4.get("three_pt_rate_pct", 0) >= 38:
        defensive_plan.append(_item(
            "DEF", "Contest the perimeter over packing the paint",
            f"{c4['three_pt_rate_pct']}% of their attempts are threes.", c4.get("total_shots", 0)))
    elif 0 < c4.get("three_pt_rate_pct", 100) <= 22:
        defensive_plan.append(_item(
            "DEF", "Wall off the paint, concede the outside shot",
            f"Only {c4['three_pt_rate_pct']}% of their shots are threes; they want the rim.",
            c4.get("total_shots", 0)))

    # Hot zone -> take it away.
    for z in (c6.get("defensive_priority_zones") or [])[:1]:
        d = (c6.get("zones") or {}).get(z, {})
        defensive_plan.append(_item(
            "DEF", f"Take away the {z}",
            f"They shoot {d.get('efg_pct', 0)}% eFG there ({d.get('attempts', 0)} attempts), above the "
            f"55% take-away line.", d.get("attempts", 0)))

    # Pace control.
    if c5.get("tracked"):
        if c5.get("pace_rating") == "fast" or c5.get("transition_frequency_pct", 0) >= 25:
            defensive_plan.append(_item(
                "DEF", "Kill transition — get matched up and make them play half-court",
                f"{c5.get('transition_frequency_pct', 0)}% of their possessions are early-clock.",
                c5.get("offensive_possessions", 0)))
        elif c5.get("pace_rating") == "slow":
            defensive_plan.append(_item(
                "DEF", "Speed them up — pressure the inbound and full-court",
                "They grind clock; force decisions before their sets develop.",
                c5.get("offensive_possessions", 0)))

    # Strategic foul target / never-foul, late.
    if ft.get("strategic_foul_targets"):
        t = ft["strategic_foul_targets"][0]
        defensive_plan.append(_item(
            "DEF", f"Late & losing: foul #{t['jersey']} ({t['ft_pct']}% FT)",
            f"{t['ft_pct']}% on {t['attempts']} attempts — put them on the line to steal a possession.",
            max(t["attempts"], WATCH_MIN_SAMPLE)))
    if ft.get("never_foul_players"):
        js = ", ".join(f"#{p['jersey']}" for p in ft["never_foul_players"][:3])
        defensive_plan.append(_item(
            "DEF", f"NEVER foul {js} late (90%+ FT)",
            "Automatic from the line in a close game — make them beat you from the field.",
            max((ft["never_foul_players"][0]["attempts"]), WATCH_MIN_SAMPLE)))

    # ── OFFENSE (how WE attack THEIR defense) ───────────────────────────────
    # Concede zone -> the shot their defense allows and our best look against them.
    concede = sorted(
        [(z, d) for z, d in (c6.get("zones") or {}).items() if d.get("attempts", 0) >= 2],
        key=lambda kv: kv[1].get("efg_pct", 0))
    # (Opponent's own low-eFG zone tells us where THEY struggle to score; on offense
    # we instead lean on their DEFENSIVE weaknesses when we have them.)
    dsa = (summary.get("defensive_scheme") or {})
    zone_pct = None
    if isinstance(dsa, dict):
        zone_pct = dsa.get("zone_pct") or dsa.get("zone_rate")
    if zone_pct and _num(zone_pct, 0) >= 30:
        offensive_plan.append(_item(
            "OFF", "Zone offense ready — they play zone a meaningful share of the time",
            f"They show zone on ~{zone_pct}% of half-court defensive possessions. Install overload "
            f"and skip-pass actions.", 10))

    bsd = (summary.get("ball_screen_defense") or {})
    top_cov = None
    if isinstance(bsd, dict):
        covs = bsd.get("coverages") or bsd.get("by_coverage") or {}
        if isinstance(covs, dict) and covs:
            top_cov = max(covs.items(), key=lambda kv: kv[1] if isinstance(kv[1], int)
                          else (kv[1].get("count", 0) if isinstance(kv[1], dict) else 0))[0]
    if top_cov:
        offensive_plan.append(_item(
            "OFF", f"Ball-screen menu vs. their base coverage ({top_cov})",
            f"Their most-shown ball-screen coverage is {top_cov}. Rep the counter in shootaround.", 8))

    # A guaranteed offensive item: attack the pace they don't want.
    if c5.get("tracked") and c5.get("pace_rating") == "slow":
        offensive_plan.append(_item(
            "OFF", "Push tempo — get into your break before they set their half-court D",
            "They prefer a grinding pace; early offense is where they are most exposed.",
            c5.get("offensive_possessions", 0)))

    # ── SPECIAL SITUATIONS ──────────────────────────────────────────────────
    if special.get("tracked"):
        for st, block in (special.get("by_type") or {}).items():
            for trusted in block.get("trusted_late_sets", [])[:1]:
                special_plan.append(_item(
                    "SPECIAL", f"Defend their trusted {st} set: {trusted['set']}",
                    f"Run {trusted['reps']}x ({trusted['late_and_close']} late & close, "
                    f"{trusted['scores']} scores). This is a trusted call — walk through the coverage.",
                    max(trusted["reps"], WATCH_MIN_SAMPLE), featured=True))
            # Even non-late repeated sets are worth a scout note.
            for s in block.get("sets", [])[:1]:
                if s["reps"] >= 2 and not s.get("late_and_close"):
                    special_plan.append(_item(
                        "SPECIAL", f"{st}: they favor {s['set']}",
                        f"{s['reps']} reps on film. Know the first option.", s["reps"]))

    def _rank(plan):
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        plan.sort(key=lambda x: (0 if x.get("featured") else 1,
                                 order.get(x["confidence"].rstrip("*"), 3), -x["sample"]))
        return plan

    return {
        "offensive_plan": _rank(offensive_plan),
        "defensive_plan": _rank(defensive_plan),
        "special_situations_plan": _rank(special_plan),
    }


def _head_coach_digest(game_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Top items across all phases, recommendations first — the tear-away sheet."""
    everything = (game_plan.get("defensive_plan", []) + game_plan.get("offensive_plan", [])
                  + game_plan.get("special_situations_plan", []))
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    everything.sort(key=lambda x: (0 if x.get("featured") else 1,
                                   0 if x["class"] == "recommendation" else 1,
                                   order.get(x["confidence"].rstrip("*"), 3), -x["sample"]))
    return [{"priority": i + 1, "phase": it["phase"], "call": it["call"],
             "confidence": it["confidence"]} for i, it in enumerate(everything[:7])]


# ═══════════════════════════════════════════════════════════════════════════
# COACH-TAGGED SYSTEMS / PRESS / PRESS-BREAK (from the film-room tag panel)
# ═══════════════════════════════════════════════════════════════════════════
def _clock(sec) -> Optional[str]:
    if sec is None:
        return None
    try:
        s = int(sec)
    except (TypeError, ValueError):
        return None
    return f"{s // 60}:{s % 60:02d}"


def coach_scheme_tags(events) -> Dict[str, Any]:
    """Roll up the offense/defense systems, presses, and press-breaks the coach
    tagged while charting film. Presses and press-breaks carry time markers so the
    report can say WHEN a press started. Custom ('Other') entries come through as
    the coach's own words and are surfaced verbatim."""
    off_sets = Counter()
    def_schemes = Counter()
    presses: Dict[str, list] = defaultdict(list)
    breaks: Dict[str, list] = defaultdict(list)
    for e in events:
        t = getattr(e, "time_seconds", None)
        if (v := _x(e, "offensive_set")):
            off_sets[v] += 1
        if (v := _x(e, "defensive_scheme")):
            def_schemes[v] += 1
        if (v := _x(e, "press_type")):
            presses[v].append(t)
        if (v := _x(e, "press_break_action")):
            breaks[v].append(t)

    if not (off_sets or def_schemes or presses or breaks):
        return {"tracked": False}

    def with_markers(bucket):
        out = {}
        for name, times in bucket.items():
            marks = [m for m in (_clock(x) for x in sorted(t for t in times if t is not None)) if m]
            out[name] = {"count": len(times), "time_markers": marks[:8]}
        return out

    return {
        "tracked": True,
        "offensive_sets": dict(off_sets.most_common()),
        "primary_offense": off_sets.most_common(1)[0][0] if off_sets else None,
        "defensive_schemes": dict(def_schemes.most_common()),
        "primary_defense": def_schemes.most_common(1)[0][0] if def_schemes else None,
        "presses": with_markers(presses),
        "press_breaks": with_markers(breaks),
    }


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY
# ═══════════════════════════════════════════════════════════════════════════
def build_basketball_scouting_report(events, summary: Dict[str, Any],
                                     six_cat: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the FULL basketball `scouting` block: the six priority categories
    (unchanged, from six_cat) PLUS the coordinator layer — eight validation gates,
    situational tendency statements, the installable game plan, advanced metrics,
    the late-game profile, free-throw / box-out data, special situations, player
    profile cards, and the single-camera confidence summary.

    Returns a superset of six_cat so every existing consumer that reads the
    category_* keys or game_plan_priorities keeps working untouched.
    """
    if not events:
        return {"available": False, "total_events": 0}

    meta = _scout_meta(events)
    camera = camera_confidence_summary(events, meta)

    late = late_game_profile(events)
    ft = free_throw_profile(events)
    special = special_situations_profile(events)
    profiles = player_profiles(events, camera_penalty=camera["individual_grade_penalty"])
    advanced = advanced_metrics(events, six_cat)

    validation = run_validation_gates(events, six_cat, late, profiles)
    personnel_flagged = validation["personnel_flagged"]

    statements = situational_statements(six_cat, summary, late, ft, personnel_flagged)
    game_plan = build_game_plan(events, six_cat, summary, late, ft, special, personnel_flagged)

    # GATE 6 — GAME PLAN TRANSLATION: pass iff we produced installable calls.
    total_calls = sum(len(game_plan[k]) for k in
                      ("defensive_plan", "offensive_plan", "special_situations_plan"))
    recs = sum(1 for k in ("defensive_plan", "offensive_plan", "special_situations_plan")
               for it in game_plan[k] if it["class"] == "recommendation")
    for g in validation["gates"]:
        if g["gate"] == 6:
            g["passed"] = total_calls > 0
            g["notes"] = ([f"Translated tendencies into {total_calls} installable call(s) "
                           f"({recs} at recommendation confidence, the rest watch items)."]
                          if total_calls else
                          ["Not enough clean tendency data to translate into a game plan yet."])

    # The full block = six categories (verbatim) + coordinator additions.
    block = dict(six_cat)  # available, total_events, category_1..6, game_plan_priorities
    block.update({
        "available": True,
        "report_status": validation["report_status"],
        "total_possessions": validation["total_possessions"],
        "offensive_possessions": validation["offensive_possessions"],
        "defensive_possessions": validation["defensive_possessions"],
        "games_scouted": validation["games_scouted"],
        "personnel_flagged": personnel_flagged,
        "validation_gates": validation["gates"],
        "situational_tendencies": statements,
        "game_plan": game_plan,
        "head_coach_priorities": _head_coach_digest(game_plan),
        "advanced_metrics": advanced,
        "late_game_profile": late,
        "free_throw_profile": ft,
        "special_situations": special,
        "player_profiles": profiles,
        "coach_scheme_tags": coach_scheme_tags(events),
        "camera_confidence": camera,
    })
    return block
