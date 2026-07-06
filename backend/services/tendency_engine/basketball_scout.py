"""
Six-category opponent scouting engine (basketball).

This module turns tagged basketball `events` (film-detected OR manually entered)
into the coach's six-category scouting brief, in STRICT ORDER OF IMPORTANCE.
Category 1 is weighted heaviest in every scoring model.

    1. TIME OF POSSESSION (player-specific)   <- weighted heaviest
    2. TURNOVERS
    3. DEFLECTIONS
    4. TEAM 2PT vs 3PT ATTEMPT RATIO
    5. PACE OF PLAY
    6. SCORING AREAS

It reads from the sport-agnostic `events` table + `extra_data` JSONB so that all
three input methods (manual entry form, CSV import, video timestamp tagging) feed
one engine and one report. No dedicated per-category tables are required.

────────────────────────────────────────────────────────────────────────────
EVENT CONTRACT (extra_data keys this engine reads)
────────────────────────────────────────────────────────────────────────────
Shared:
    primary_player_jersey : str   the actor (ball-handler, shooter, defender)
    players               : list[{jersey, team, role}]
    quarter               : int   1..4 (5+ = OT)
    possession_seconds    : float seconds the actor/team held the ball
    score_diff_at_start   : int   scouted team's margin at possession start (+lead/-trail)

event_type == "shot":
    result            : "made" | "missed" | "and-1"
    shot_zone         : one of the 10 court zones (see COURT_ZONES)
    shot_type         : "2pt" | "3pt"   (inferred from zone if absent)
    possession_origin : "half_court" | "transition" | "set" | "broken" | "pnr"

event_type == "turnover":
    turnover_type        : "live_ball_steal"|"bad_pass"|"charge"|"travel"|
                           "shot_clock"|"out_of_bounds"
    game_situation       : "half_court"|"transition"|"press"|"late_game"
    generated_by_defender: str  opponent defender jersey who forced it

event_type == "deflection" (side == "defense", actor = the defender):
    deflection_type              : "tipped_pass"|"contested_catch"|"redirected_dribble"
    resulted_in_possession_change: bool
    passing_lane                 : str  e.g. "wing_entry", "post_entry", "skip"

event_type == "possession" (pace ledger; one per possession):
    possession_seconds  : float
    possession_origin   : "transition" | "half_court" | ...
    side                : "offense" | "defense"
    score_diff_at_start : int

event_type == "player_stat" (aggregate quick-entry; one row per player):
    possession_time_seconds, touches, turnovers, deflections,
    shot_attempts_2pt, shot_attempts_3pt, shot_makes_2pt, shot_makes_3pt
────────────────────────────────────────────────────────────────────────────
"""
from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict
import statistics

# The ten court zones, in the exact taxonomy the charter specifies.
COURT_ZONES = [
    "Restricted Area", "Paint Non-RA",
    "Mid-Range Left", "Mid-Range Right", "Mid-Range Center",
    "Left Corner 3", "Right Corner 3",
    "Above-the-Break 3 Left", "Above-the-Break 3 Right", "Above-the-Break 3 Center",
]
THREE_ZONES = {
    "Left Corner 3", "Right Corner 3",
    "Above-the-Break 3 Left", "Above-the-Break 3 Right", "Above-the-Break 3 Center",
}
PAINT_ZONES = {"Restricted Area", "Paint Non-RA"}
MID_ZONES = {"Mid-Range Left", "Mid-Range Right", "Mid-Range Center"}

# Charter thresholds (single source of truth for every flag in the report).
ISO_DEPENDENCY_PCT = 35.0      # C1: one player > 35% of team possession time
DEAD_ZONE_SECONDS = 1.0       # C1: avg sec/touch below this = catch-and-pass "ghost"
DEAD_ZONE_MIN_TOUCHES = 4     # C1: need enough touches to call it a pattern
PERIMETER_DEPENDENCY_PCT = 40.0  # C4: player's 3PA > 40% of their shots
HOT_ZONE_EFG = 55.0           # C6: zone eFG% above this must be taken away
PATTERN_MIN_SAME_TYPE = 2     # C2: 2+ turnovers of the same type = pattern
HS_GIRLS_QUARTER_MINUTES = 8  # AL HS girls quarters are 8:00 (for per-10-min rate)


# ── low-level accessors ────────────────────────────────────────────────────
def _x(e, key, default=None):
    ed = getattr(e, "extra_data", None)
    if not ed:
        return default
    return ed.get(key, default)


def _jersey(e) -> Optional[str]:
    # Prefer the first-class column (migration 013); fall back to extra_data.
    j = getattr(e, "player", None) or _x(e, "primary_player_jersey")
    return str(j) if j not in (None, "") else None


def _made(e) -> bool:
    return (getattr(e, "result", None) or "").lower() in ("made", "good", "and-1")


def _shot_is_three(e) -> bool:
    st = (_x(e, "shot_type") or "").lower()
    if st in ("3pt", "3", "three"):
        return True
    if st in ("2pt", "2", "two"):
        return False
    return (_x(e, "shot_zone") or "") in THREE_ZONES


def _side(e) -> str:
    return (getattr(e, "side", None) or "offense").lower()


def _is_offense(e) -> bool:
    return _side(e) in ("offense", "transition")


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _pct(part: int, whole: int, ndigits: int = 1) -> float:
    return round(part / whole * 100, ndigits) if whole else 0.0


def _efg(makes_2: int, makes_3: int, attempts: int) -> float:
    """Effective FG% credits a made three as 1.5 made twos: (FGM + 0.5*3PM)/FGA."""
    if not attempts:
        return 0.0
    return round((makes_2 + makes_3 + 0.5 * makes_3) / attempts * 100, 1)


def _estimate_game_minutes(events) -> int:
    quarters = {int(q) for e in events if (q := _x(e, "quarter")) is not None}
    n = len(quarters) if quarters else 4
    return n * HS_GIRLS_QUARTER_MINUTES


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 1 — TIME OF POSSESSION (player-specific)  [weighted heaviest]
# ═══════════════════════════════════════════════════════════════════════════
def _category_1_possession(events) -> Dict[str, Any]:
    """Rank players by possession time, classify role, flag isolation dependency."""
    # Aggregate per player from granular events and/or aggregate player_stat rows.
    agg: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"seconds": 0.0, "touches": 0, "jersey": None}
    )

    for e in events:
        j = _jersey(e)
        if not j:
            continue
        if e.event_type == "player_stat":
            agg[j]["jersey"] = j
            agg[j]["seconds"] += _num(_x(e, "possession_time_seconds"))
            agg[j]["touches"] += int(_num(_x(e, "touches")))
        elif _is_offense(e) and e.event_type in ("shot", "turnover", "possession", "touch"):
            secs = _num(_x(e, "possession_seconds"))
            agg[j]["jersey"] = j
            agg[j]["seconds"] += secs
            agg[j]["touches"] += 1

    players = {j: a for j, a in agg.items() if a["touches"] > 0 or a["seconds"] > 0}
    if not players:
        return {"tracked": False, "players": []}

    team_seconds = sum(a["seconds"] for a in players.values()) or 0.0
    team_touches = sum(a["touches"] for a in players.values()) or 0

    rows = []
    for j, a in players.items():
        secs = round(a["seconds"], 1)
        touches = int(a["touches"])
        avg_per_touch = round(secs / touches, 2) if touches else 0.0
        share = _pct(int(secs), int(team_seconds)) if team_seconds else 0.0

        # Role classification (initiator / role player / ghost).
        is_dead_zone = touches >= DEAD_ZONE_MIN_TOUCHES and avg_per_touch < DEAD_ZONE_SECONDS
        if is_dead_zone or (touches and share < 6 and avg_per_touch < DEAD_ZONE_SECONDS):
            role = "ghost"
        elif share >= 20 or (avg_per_touch >= 3.0 and touches >= DEAD_ZONE_MIN_TOUCHES):
            role = "initiator"
        else:
            role = "role_player"

        rows.append({
            "jersey": j,
            "possession_seconds": secs,
            "touches": touches,
            "avg_seconds_per_touch": avg_per_touch,
            "possession_share_pct": share,
            "role": role,
            "dead_zone": is_dead_zone,
        })

    rows.sort(key=lambda r: (r["possession_seconds"], r["touches"]), reverse=True)

    primary = rows[0] if rows else None
    iso_flag = bool(primary and primary["possession_share_pct"] > ISO_DEPENDENCY_PCT)
    initiators = [r["jersey"] for r in rows if r["role"] == "initiator"]
    ghosts = [r["jersey"] for r in rows if r["role"] == "ghost"]

    return {
        "tracked": True,
        "players": rows,
        "team_possession_seconds": round(team_seconds, 1),
        "team_touches": team_touches,
        "primary_ball_handler": primary["jersey"] if primary else None,
        "primary_share_pct": primary["possession_share_pct"] if primary else 0.0,
        "secondary_initiators": initiators[1:] if len(initiators) > 1 else [],
        "ghost_players": ghosts,
        "isolation_dependency_flag": iso_flag,
        "dead_zone_players": [r["jersey"] for r in rows if r["dead_zone"]],
    }


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 2 — TURNOVERS
# ═══════════════════════════════════════════════════════════════════════════
def _category_2_turnovers(events) -> Dict[str, Any]:
    tos = [e for e in events if e.event_type == "turnover"]
    off_possessions = _offensive_possession_count(events)
    game_minutes = _estimate_game_minutes(events)

    # Aggregate player_stat turnover counts (quick-entry) supplement granular rows.
    stat_tos = {
        _jersey(e): int(_num(_x(e, "turnovers")))
        for e in events if e.event_type == "player_stat" and _jersey(e)
    }

    if not tos and not any(stat_tos.values()):
        return {"total": 0}

    by_type = Counter((_x(e, "turnover_type") or "unspecified") for e in tos)
    by_situation = Counter((_x(e, "game_situation") or "unspecified") for e in tos)
    by_defender = Counter(
        d for e in tos if (d := _x(e, "generated_by_defender"))
    )

    # Per-player, with same-type pattern detection (2+ of one type).
    per_player_types: Dict[str, Counter] = defaultdict(Counter)
    for e in tos:
        j = _jersey(e)
        if j:
            per_player_types[j][_x(e, "turnover_type") or "unspecified"] += 1

    players = []
    all_jerseys = set(per_player_types) | set(stat_tos)
    for j in all_jerseys:
        granular = sum(per_player_types[j].values())
        total_j = max(granular, stat_tos.get(j, 0))
        patterns = [
            {"type": t, "count": c}
            for t, c in per_player_types[j].items()
            if c >= PATTERN_MIN_SAME_TYPE
        ]
        players.append({
            "jersey": j,
            "turnovers": total_j,
            "by_type": dict(per_player_types[j]),
            "rate_per_possession": round(total_j / off_possessions, 3) if off_possessions else None,
            "rate_per_10_min": round(total_j / game_minutes * 10, 2) if game_minutes else None,
            "pattern_flags": patterns,
        })
    players.sort(key=lambda p: p["turnovers"], reverse=True)

    total = sum(p["turnovers"] for p in players) or len(tos)
    return {
        "total": total,
        "by_type": dict(by_type.most_common()),
        "by_situation": dict(by_situation.most_common()),
        "generated_by_defender": dict(by_defender.most_common(6)),
        "team_rate_per_possession": round(total / off_possessions, 3) if off_possessions else None,
        "team_rate_per_10_min": round(total / game_minutes * 10, 2) if game_minutes else None,
        "offensive_possessions": off_possessions,
        "estimated_game_minutes": game_minutes,
        "players": players,
        "most_dangerous_defender": by_defender.most_common(1)[0][0] if by_defender else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 3 — DEFLECTIONS
# ═══════════════════════════════════════════════════════════════════════════
def _category_3_deflections(events) -> Dict[str, Any]:
    defl = [e for e in events if e.event_type == "deflection"]
    stat_defl = {
        _jersey(e): int(_num(_x(e, "deflections")))
        for e in events if e.event_type == "player_stat" and _jersey(e)
    }
    def_possessions = _defensive_possession_count(events)

    if not defl and not any(stat_defl.values()):
        return {"total": 0}

    changed = [e for e in defl if _x(e, "resulted_in_possession_change")]
    by_lane = Counter((_x(e, "passing_lane") or "unspecified") for e in defl)

    per_player: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "changed": 0})
    for e in defl:
        j = _jersey(e)
        if not j:
            continue
        per_player[j]["total"] += 1
        if _x(e, "resulted_in_possession_change"):
            per_player[j]["changed"] += 1
    for j, c in stat_defl.items():
        if c > per_player[j]["total"]:
            per_player[j]["total"] = c

    players = []
    for j, d in per_player.items():
        players.append({
            "jersey": j,
            "deflections": d["total"],
            "possession_changes": d["changed"],
            "conversion_pct": _pct(d["changed"], d["total"]),
            "per_defensive_possession": round(d["total"] / def_possessions, 3) if def_possessions else None,
        })
    players.sort(key=lambda p: p["deflections"], reverse=True)

    total = sum(p["deflections"] for p in players) or len(defl)
    return {
        "total": total,
        "resulted_in_possession_change": len(changed),
        "incomplete": total - len(changed),
        "conversion_pct": _pct(len(changed), total),
        "passing_lane_vulnerability": dict(by_lane.most_common()),
        "most_vulnerable_lane": by_lane.most_common(1)[0][0] if by_lane else None,
        "defensive_possessions": def_possessions,
        "players": players,
        # Their best deflection defender = our neutralize-first target.
        "neutralize_first_defender": players[0]["jersey"] if players else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 4 — TEAM 2PT vs 3PT ATTEMPT RATIO
# ═══════════════════════════════════════════════════════════════════════════
def _category_4_shot_ratio(events) -> Dict[str, Any]:
    shots = [e for e in events if e.event_type == "shot" and _is_offense(e)]

    # Fold aggregate player_stat attempts into totals + per-player classification.
    stat_rows = [e for e in events if e.event_type == "player_stat"]

    if not shots and not stat_rows:
        return {"total_shots": 0}

    def split(shot_list):
        twos = [e for e in shot_list if not _shot_is_three(e)]
        threes = [e for e in shot_list if _shot_is_three(e)]
        return len(twos), len(threes)

    total_2, total_3 = split(shots)

    # by half (Q1-2 vs Q3-4+) and 4th-quarter / trailing shift
    first_half = [e for e in shots if (int(_num(_x(e, "quarter"), 0)) in (1, 2))]
    second_half = [e for e in shots if (int(_num(_x(e, "quarter"), 0)) >= 3)]
    fourth = [e for e in shots if int(_num(_x(e, "quarter"), 0)) == 4]
    trailing = [e for e in shots if _num(_x(e, "score_diff_at_start"), 0) < 0]

    # by possession origin (pick-and-roll / transition / set / broken)
    by_origin: Dict[str, Dict[str, int]] = defaultdict(lambda: {"2pt": 0, "3pt": 0})
    for e in shots:
        origin = _x(e, "possession_origin") or "unspecified"
        by_origin[origin]["3pt" if _shot_is_three(e) else "2pt"] += 1

    def ratio_block(shot_list):
        t2, t3 = split(shot_list)
        tot = t2 + t3
        return {
            "attempts_2pt": t2,
            "attempts_3pt": t3,
            "total": tot,
            "three_pt_rate_pct": _pct(t3, tot),
            "ratio_2pt_to_3pt": round(t2 / t3, 2) if t3 else None,
        }

    # Per-player 3PT dependency (>40% of personal attempts) + tendency class.
    per_player: Dict[str, Dict[str, int]] = defaultdict(lambda: {"2pt": 0, "3pt": 0, "paint": 0, "mid": 0})
    for e in shots:
        j = _jersey(e)
        if not j:
            continue
        zone = _x(e, "shot_zone") or ""
        if _shot_is_three(e):
            per_player[j]["3pt"] += 1
        else:
            per_player[j]["2pt"] += 1
        if zone in PAINT_ZONES:
            per_player[j]["paint"] += 1
        elif zone in MID_ZONES:
            per_player[j]["mid"] += 1
    for e in stat_rows:
        j = _jersey(e)
        if not j:
            continue
        per_player[j]["2pt"] += int(_num(_x(e, "shot_attempts_2pt")))
        per_player[j]["3pt"] += int(_num(_x(e, "shot_attempts_3pt")))

    total_2 = total_2 or sum(p["2pt"] for p in per_player.values())
    total_3 = total_3 or sum(p["3pt"] for p in per_player.values())

    player_rows = []
    for j, s in per_player.items():
        pa = s["2pt"] + s["3pt"]
        if pa == 0:
            continue
        three_rate = _pct(s["3pt"], pa)
        paint_rate = _pct(s["paint"], pa)
        mid_rate = _pct(s["mid"], pa)
        if three_rate > PERIMETER_DEPENDENCY_PCT:
            tendency = "perimeter"
        elif paint_rate >= 50:
            tendency = "paint_attacker"
        elif mid_rate >= max(three_rate, paint_rate):
            tendency = "mid_range"
        else:
            tendency = "balanced"
        player_rows.append({
            "jersey": j,
            "attempts": pa,
            "attempts_2pt": s["2pt"],
            "attempts_3pt": s["3pt"],
            "three_pt_rate_pct": three_rate,
            "tendency": tendency,
            "perimeter_dependency_flag": three_rate > PERIMETER_DEPENDENCY_PCT and pa >= 4,
        })
    player_rows.sort(key=lambda p: p["attempts"], reverse=True)

    total = total_2 + total_3
    # 4th-quarter / trailing behavior: do they jack threes or attack paint?
    fourth_rate = ratio_block(fourth)["three_pt_rate_pct"] if fourth else None
    overall_rate = _pct(total_3, total)
    late_game_shift = None
    if fourth_rate is not None:
        if fourth_rate - overall_rate >= 8:
            late_game_shift = "goes_small_jacks_threes"
        elif overall_rate - fourth_rate >= 8:
            late_game_shift = "attacks_the_paint"
        else:
            late_game_shift = "consistent"

    return {
        "total_shots": total,
        "attempts_2pt": total_2,
        "attempts_3pt": total_3,
        "three_pt_rate_pct": overall_rate,
        "ratio_2pt_to_3pt": round(total_2 / total_3, 2) if total_3 else None,
        "by_half": {"first": ratio_block(first_half), "second": ratio_block(second_half)},
        "fourth_quarter": ratio_block(fourth),
        "when_trailing": ratio_block(trailing),
        "late_game_shift": late_game_shift,
        "by_possession_origin": {
            k: {**v, "three_pt_rate_pct": _pct(v["3pt"], v["2pt"] + v["3pt"])}
            for k, v in by_origin.items()
        },
        "players": player_rows,
        "perimeter_dependent_players": [p["jersey"] for p in player_rows if p["perimeter_dependency_flag"]],
    }


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 5 — PACE OF PLAY
# ═══════════════════════════════════════════════════════════════════════════
def _category_5_pace(events) -> Dict[str, Any]:
    # A possession is any event carrying possession_seconds, or an explicit
    # "possession" ledger event. Prefer explicit possession rows when present.
    poss = [e for e in events if e.event_type == "possession"]
    if not poss:
        poss = [e for e in events
                if _x(e, "possession_seconds") is not None
                and e.event_type in ("shot", "turnover", "touch")]
    if not poss:
        return {"tracked": False}

    off = [e for e in poss if _is_offense(e)]
    deff = [e for e in poss if _side(e) == "defense"]

    def avg_secs(rows):
        vals = [_num(_x(e, "possession_seconds")) for e in rows if _x(e, "possession_seconds") is not None]
        return round(statistics.mean(vals), 1) if vals else None, vals

    off_avg, off_vals = avg_secs(off)
    def_avg, def_vals = avg_secs(deff)

    # Transition frequency: possessions beginning within 5s of a change (origin
    # transition, or a possession that produced a shot in <= 5 seconds).
    def is_transition(e):
        if (_x(e, "possession_origin") or "").lower() == "transition":
            return True
        s = _x(e, "possession_seconds")
        return s is not None and _num(s) <= 5.0
    trans = [e for e in off if is_transition(e)]
    transition_pct = _pct(len(trans), len(off))

    # Leading vs trailing pace shift.
    lead = [_num(_x(e, "possession_seconds")) for e in off if _num(_x(e, "score_diff_at_start"), 0) > 0 and _x(e, "possession_seconds") is not None]
    trail = [_num(_x(e, "possession_seconds")) for e in off if _num(_x(e, "score_diff_at_start"), 0) < 0 and _x(e, "possession_seconds") is not None]
    lead_avg = round(statistics.mean(lead), 1) if lead else None
    trail_avg = round(statistics.mean(trail), 1) if trail else None

    situational = None
    if lead_avg is not None and trail_avg is not None:
        if trail_avg + 2 < lead_avg:
            situational = "speeds_up_when_trailing"
        elif lead_avg + 2 < trail_avg:
            situational = "slows_down_when_trailing"
        else:
            situational = "pace_holds_regardless_of_score"

    # Coach-controlled (consistent) vs player-driven (variable): stdev of offense.
    control = None
    stdev = None
    if len(off_vals) >= 4:
        stdev = round(statistics.pstdev(off_vals), 1)
        control = "coach_controlled" if stdev <= 5.0 else "player_driven"

    # Pace rating from average offensive possession length.
    if off_avg is None:
        rating = "unknown"
    elif off_avg < 13:
        rating = "fast"
    elif off_avg <= 17:
        rating = "moderate"
    else:
        rating = "slow"

    return {
        "tracked": True,
        "offensive_possessions": len(off),
        "defensive_possessions": len(deff),
        "avg_offensive_possession_seconds": off_avg,
        "avg_defensive_possession_seconds": def_avg,
        "transition_frequency_pct": transition_pct,
        "pace_rating": rating,
        "avg_seconds_when_leading": lead_avg,
        "avg_seconds_when_trailing": trail_avg,
        "situational_pace": situational,
        "possession_length_stdev": stdev,
        "pace_control": control,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 6 — SCORING AREAS (eFG% by zone, team + player)
# ═══════════════════════════════════════════════════════════════════════════
def _category_6_scoring_areas(events) -> Dict[str, Any]:
    shots = [e for e in events if e.event_type == "shot" and _is_offense(e)]
    if not shots:
        return {"total_shots": 0}

    def zone_block(shot_list):
        zones: Dict[str, Dict[str, int]] = defaultdict(lambda: {"att": 0, "m2": 0, "m3": 0})
        for e in shot_list:
            z = _x(e, "shot_zone")
            if not z:
                continue
            zb = zones[z]
            zb["att"] += 1
            if _made(e):
                if _shot_is_three(e):
                    zb["m3"] += 1
                else:
                    zb["m2"] += 1
        out = {}
        for z, zb in zones.items():
            made = zb["m2"] + zb["m3"]
            out[z] = {
                "attempts": zb["att"],
                "made": made,
                "fg_pct": _pct(made, zb["att"]),
                "efg_pct": _efg(zb["m2"], zb["m3"], zb["att"]),
                "pct_of_shots": _pct(zb["att"], len(shot_list)),
            }
        return out

    team_zones = zone_block(shots)
    total_att = len(shots)
    total_m2 = sum(1 for e in shots if _made(e) and not _shot_is_three(e))
    total_m3 = sum(1 for e in shots if _made(e) and _shot_is_three(e))

    # Comfort zones (high attempt AND high make) vs avoid zones (low make / low use).
    scored = [(z, d) for z, d in team_zones.items() if d["attempts"] >= 2]
    comfort = sorted(scored, key=lambda kv: (kv[1]["efg_pct"], kv[1]["attempts"]), reverse=True)
    avoid = sorted(scored, key=lambda kv: (kv[1]["efg_pct"], kv[1]["attempts"]))
    priority_zones = [z for z, d in team_zones.items() if d["efg_pct"] >= HOT_ZONE_EFG and d["attempts"] >= 2]

    # Per-player zone eFG%.
    by_player_zone: Dict[str, Dict[str, list]] = defaultdict(list)
    for e in shots:
        j = _jersey(e)
        if j:
            by_player_zone[j].append(e)
    player_rows = []
    for j, ps in by_player_zone.items():
        pm2 = sum(1 for e in ps if _made(e) and not _shot_is_three(e))
        pm3 = sum(1 for e in ps if _made(e) and _shot_is_three(e))
        player_rows.append({
            "jersey": j,
            "attempts": len(ps),
            "efg_pct": _efg(pm2, pm3, len(ps)),
            "zones": zone_block(ps),
        })
    player_rows.sort(key=lambda p: p["attempts"], reverse=True)

    return {
        "total_shots": total_att,
        "team_efg_pct": _efg(total_m2, total_m3, total_att),
        "team_fg_pct": _pct(total_m2 + total_m3, total_att),
        "zones": team_zones,
        "top_scoring_zones": [{"zone": z, **d} for z, d in comfort[:3]],
        "avoid_zones": [{"zone": z, **d} for z, d in avoid[:3]],
        "defensive_priority_zones": priority_zones,  # eFG > 55% -> take these away
        "players": player_rows,
    }


# ═══════════════════════════════════════════════════════════════════════════
# possession counting helpers (shared by C2 / C3 / C5)
# ═══════════════════════════════════════════════════════════════════════════
def _offensive_possession_count(events) -> int:
    explicit = [e for e in events if e.event_type == "possession" and _is_offense(e)]
    if explicit:
        return len(explicit)
    # Fall back to counting offensive shots + turnovers as possession endings.
    return len([e for e in events if _is_offense(e) and e.event_type in ("shot", "turnover")])


def _defensive_possession_count(events) -> int:
    explicit = [e for e in events if e.event_type == "possession" and _side(e) == "defense"]
    if explicit:
        return len(explicit)
    defl = [e for e in events if e.event_type == "deflection"]
    # Approximate opponent (our-team) offensive possessions faced.
    faced = len([e for e in events if _side(e) == "defense" and e.event_type in ("shot", "turnover")])
    return faced or len(defl)


# ═══════════════════════════════════════════════════════════════════════════
# GAME PLAN PRIORITIES — top 3 defensive adjustments (Category 1 weighted heaviest)
# ═══════════════════════════════════════════════════════════════════════════
def _game_plan_priorities(c1, c2, c3, c4, c5, c6) -> List[Dict[str, Any]]:
    """Auto-generate ranked defensive adjustments. Weight reflects category priority:
    Category 1 findings outrank Category 6 findings when leverage is comparable."""
    candidates: List[Dict[str, Any]] = []

    # C1 (weight 6) — isolation dependency is the single highest-leverage tell.
    if c1.get("isolation_dependency_flag") and c1.get("primary_ball_handler"):
        candidates.append({
            "weight": 6.0 + c1.get("primary_share_pct", 0) / 100,
            "category": "Time of Possession",
            "adjustment": (
                f"Deny #{c1['primary_ball_handler']} the ball. They control "
                f"{c1.get('primary_share_pct', 0)}% of possession time, well over the 35% "
                f"isolation-dependency line. Trap on the catch and force secondary handlers to create."
            ),
        })
    for ghost in c1.get("ghost_players", [])[:1]:
        candidates.append({
            "weight": 5.4,
            "category": "Time of Possession",
            "adjustment": (
                f"Sag off #{ghost} (a non-creator who catches and passes immediately) and load help "
                f"toward the primary handler. Dare #{ghost} to make a play."
            ),
        })

    # C2 (weight 5) — force the turnover-prone player / situation.
    if c2.get("total") and c2.get("players"):
        top = c2["players"][0]
        if top["turnovers"] >= 2:
            situ = next(iter(c2.get("by_situation", {})), None)
            candidates.append({
                "weight": 5.0 + top["turnovers"] / 20,
                "category": "Turnovers",
                "adjustment": (
                    f"Pressure #{top['jersey']} ({top['turnovers']} turnovers"
                    + (f", pattern in {top['pattern_flags'][0]['type']}" if top.get("pattern_flags") else "")
                    + (f"; team most vulnerable in {situ}" if situ and situ != 'unspecified' else "")
                    + "). Turn them over early to set tempo."
                ),
            })

    # C3 (weight 4) — neutralize their best deflection defender.
    if c3.get("neutralize_first_defender"):
        lane = c3.get("most_vulnerable_lane")
        candidates.append({
            "weight": 4.0,
            "category": "Deflections",
            "adjustment": (
                f"Attack away from #{c3['neutralize_first_defender']}, their top deflection defender. "
                + (f"Stop feeding the {lane} lane where they live." if lane and lane != 'unspecified' else "Vary entry angles to avoid their active hands.")
            ),
        })

    # C4 (weight 3) — take away the shot they lean on.
    if c4.get("total_shots"):
        if c4.get("perimeter_dependent_players"):
            js = ", ".join(f"#{j}" for j in c4["perimeter_dependent_players"][:3])
            candidates.append({
                "weight": 3.4,
                "category": "Shot Selection",
                "adjustment": f"Run {js} off the 3-point line. Over 40% of their shots are threes; close out high and force drives.",
            })
        elif c4.get("three_pt_rate_pct", 0) >= 38:
            candidates.append({
                "weight": 3.0,
                "category": "Shot Selection",
                "adjustment": f"Contest the perimeter. {c4['three_pt_rate_pct']}% of their attempts are threes. Prioritize closeouts over paint packing.",
            })
        elif c4.get("three_pt_rate_pct", 100) <= 22:
            candidates.append({
                "weight": 3.0,
                "category": "Shot Selection",
                "adjustment": f"Wall off the paint. Only {c4['three_pt_rate_pct']}% of their shots are threes; they want the rim. Build a help wall and make them shoot outside.",
            })

    # C5 (weight 2) — control tempo against their preference.
    if c5.get("tracked"):
        if c5.get("pace_rating") == "fast" or (c5.get("transition_frequency_pct", 0) >= 25):
            candidates.append({
                "weight": 2.4,
                "category": "Pace",
                "adjustment": f"Kill transition. {c5.get('transition_frequency_pct', 0)}% of their possessions are early-clock; get matched up and make them play half-court.",
            })
        elif c5.get("pace_rating") == "slow":
            candidates.append({
                "weight": 2.0,
                "category": "Pace",
                "adjustment": "Speed them up. They grind clock (slow pace); pressure the inbound and full-court to force decisions before their sets develop.",
            })

    # C6 (weight 1) — take away the hot zone.
    for z in c6.get("defensive_priority_zones", [])[:1]:
        d = c6.get("zones", {}).get(z, {})
        candidates.append({
            "weight": 1.0 + d.get("efg_pct", 0) / 100,
            "category": "Scoring Areas",
            "adjustment": f"Take away the {z}. They shoot {d.get('efg_pct', 0)}% eFG there ({d.get('attempts', 0)} attempts), above the 55% take-it-away line.",
        })

    candidates.sort(key=lambda c: c["weight"], reverse=True)
    return [
        {"priority": i + 1, "category": c["category"], "adjustment": c["adjustment"]}
        for i, c in enumerate(candidates[:3])
    ]


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY
# ═══════════════════════════════════════════════════════════════════════════
def build_scouting_report(events) -> Dict[str, Any]:
    """Compute all six priority categories + the auto game-plan. Returns the
    `scouting` block that gets merged into the basketball tendency summary."""
    if not events:
        return {"available": False, "total_events": 0}

    c1 = _category_1_possession(events)
    c2 = _category_2_turnovers(events)
    c3 = _category_3_deflections(events)
    c4 = _category_4_shot_ratio(events)
    c5 = _category_5_pace(events)
    c6 = _category_6_scoring_areas(events)

    return {
        "available": True,
        "total_events": len(events),
        # ordered explicitly so downstream consumers see priority order
        "category_1_time_of_possession": c1,
        "category_2_turnovers": c2,
        "category_3_deflections": c3,
        "category_4_shot_ratio": c4,
        "category_5_pace": c5,
        "category_6_scoring_areas": c6,
        "game_plan_priorities": _game_plan_priorities(c1, c2, c3, c4, c5, c6),
    }
