from typing import List, Dict, Any
from collections import Counter, defaultdict

RUN_TYPES = {"run", "draw", "option", "qb sneak", "rush", "counter", "sweep", "power", "iso", "trap"}

# New deep-extraction fields live in extra_data until post-beta column migration
def _x(e, key, default=None):
    """Read a deep-extraction field from extra_data."""
    ed = getattr(e, "extra_data", None)
    if not ed:
        return default
    return ed.get(key, default)
PASS_TYPES = {"pass", "screen", "rpo", "play action", "play-action", "dropback", "rollout", "bootleg", "quick game"}
SPECIAL_TYPES = {"punt", "kickoff", "field goal", "pat", "kick", "onside"}

# Success rate thresholds (standard football analytics)
# 1st down: gain >= 4 yards
# 2nd down: gain >= 50% of distance needed
# 3rd/4th down: convert (result contains "conversion" or yards >= distance)
SUCCESS_1ST = 4


def _is_play(e) -> bool:
    return e.event_type == "play" or e.event_type in ("run", "pass", "kick", "penalty") or bool(e.play_type)


def _kind(e) -> str:
    """Return 'run' | 'pass' | 'special' | 'other' for an event."""
    pt = (e.play_type or "").strip().lower()
    if pt in RUN_TYPES:
        return "run"
    if pt in PASS_TYPES:
        return "pass"
    if pt in SPECIAL_TYPES:
        return "special"
    if e.event_type == "run":
        return "run"
    if e.event_type == "pass":
        return "pass"
    if e.event_type == "kick":
        return "special"
    return "other"


def _is_run(e) -> bool:
    return _kind(e) == "run"


def _is_pass(e) -> bool:
    return _kind(e) == "pass"


def _is_success(e) -> bool:
    """Standard football success rate: positive expected-value play."""
    yards = e.yards_gained
    if yards is None:
        return False
    down = e.down
    distance = e.distance
    if down == 1:
        return yards >= SUCCESS_1ST
    if down == 2 and distance:
        return yards >= distance * 0.5
    if down in (3, 4) and distance:
        return yards >= distance
    return yards > 0


def _is_explosive(e) -> bool:
    """Explosive play: run 10+ yards or pass 15+ yards."""
    yards = e.yards_gained
    if yards is None:
        return False
    if _is_run(e):
        return yards >= 10
    if _is_pass(e):
        return yards >= 15
    return False


def _is_negative(e) -> bool:
    """Negative play: loss of yards or sack."""
    yards = e.yards_gained
    result = (e.result or "").lower()
    if yards is not None and yards < 0:
        return True
    if "sack" in result or "loss" in result or "tackle for loss" in result:
        return True
    return False


def _down_summary(plays) -> dict:
    if not plays:
        return {"total": 0}
    runs = [p for p in plays if _is_run(p)]
    passes = [p for p in plays if _is_pass(p)]
    rp = len(runs) + len(passes)
    yards = [p.yards_gained for p in plays if p.yards_gained is not None]
    successes = [p for p in plays if _is_success(p)]
    return {
        "total": len(plays),
        "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
        "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
        "success_rate": round(len(successes) / len(plays) * 100, 1) if plays else 0,
        "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
        "top_plays": dict(Counter(p.play_type for p in plays if p.play_type).most_common(5)),
        "top_formations": dict(Counter(p.formation for p in plays if p.formation).most_common(3)),
    }


def _formation_play_matrix(plays) -> Dict[str, Any]:
    """For each formation: run/pass split, top plays, avg yards."""
    by_formation = defaultdict(list)
    for e in plays:
        if e.formation:
            by_formation[e.formation].append(e)

    matrix = {}
    for formation, fp in sorted(by_formation.items(), key=lambda x: -len(x[1]))[:10]:
        runs = [p for p in fp if _is_run(p)]
        passes = [p for p in fp if _is_pass(p)]
        rp = len(runs) + len(passes)
        yards = [p.yards_gained for p in fp if p.yards_gained is not None]
        successes = [p for p in fp if _is_success(p)]
        matrix[formation] = {
            "count": len(fp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(fp) * 100, 1) if fp else 0,
            "top_plays": dict(Counter(p.play_type for p in fp if p.play_type).most_common(4)),
        }
    return matrix


def _yards_by_play_type(plays) -> Dict[str, Any]:
    """Avg yards, count, and success rate per play type."""
    by_type = defaultdict(list)
    for e in plays:
        if e.play_type:
            by_type[e.play_type].append(e)

    result = {}
    for pt, pp in sorted(by_type.items(), key=lambda x: -len(x[1]))[:12]:
        yards = [p.yards_gained for p in pp if p.yards_gained is not None]
        successes = [p for p in pp if _is_success(p)]
        explosives = [p for p in pp if _is_explosive(p)]
        result[pt] = {
            "count": len(pp),
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(pp) * 100, 1) if pp else 0,
            "explosive_count": len(explosives),
        }
    return result


def _hash_play_matrix(plays) -> Dict[str, Any]:
    """Per hash: run/pass split, top play types, avg yards."""
    by_hash = defaultdict(list)
    for e in plays:
        if e.hash_position:
            by_hash[e.hash_position].append(e)

    matrix = {}
    for h, hp in by_hash.items():
        runs = [p for p in hp if _is_run(p)]
        passes = [p for p in hp if _is_pass(p)]
        rp = len(runs) + len(passes)
        yards = [p.yards_gained for p in hp if p.yards_gained is not None]
        matrix[h] = {
            "count": len(hp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "top_plays": dict(Counter(p.play_type for p in hp if p.play_type).most_common(3)),
        }
    return matrix


def _motion_analysis(plays) -> Dict[str, Any]:
    """Motion vs. no-motion split: run/pass %, avg yards, success rate."""
    with_motion = [e for e in plays if e.motion]
    without_motion = [e for e in plays if not e.motion]

    def _summary(pp):
        if not pp:
            return {"count": 0}
        runs = [p for p in pp if _is_run(p)]
        passes = [p for p in pp if _is_pass(p)]
        rp = len(runs) + len(passes)
        yards = [p.yards_gained for p in pp if p.yards_gained is not None]
        successes = [p for p in pp if _is_success(p)]
        return {
            "count": len(pp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(pp) * 100, 1) if pp else 0,
        }

    return {
        "with_motion": _summary(with_motion),
        "without_motion": _summary(without_motion),
        "motion_pct": round(len(with_motion) / len(plays) * 100, 1) if plays else 0,
    }


def _red_zone_detail(plays) -> Dict[str, Any]:
    """Detailed red zone breakdown: formations, play types, success rate, scoring rate."""
    rz = [e for e in plays if e.field_position and _is_red_zone(e.field_position)]
    if not rz:
        return {"total": 0}

    runs = [e for e in rz if _is_run(e)]
    passes = [e for e in rz if _is_pass(e)]
    rp = len(runs) + len(passes)
    successes = [e for e in rz if _is_success(e)]
    scores = [e for e in rz if (e.result or "").lower() in ("td", "touchdown", "score")]

    return {
        "total": len(rz),
        "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
        "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
        "success_rate": round(len(successes) / len(rz) * 100, 1) if rz else 0,
        "scoring_plays": len(scores),
        "top_formations": dict(Counter(e.formation for e in rz if e.formation).most_common(5)),
        "top_plays": dict(Counter(e.play_type for e in rz if e.play_type).most_common(5)),
        "personnel": dict(Counter(e.personnel for e in rz if e.personnel).most_common(4)),
    }


def _explosive_negative_analysis(plays) -> Dict[str, Any]:
    """Explosive plays (10+ run / 15+ pass) and negative plays (TFL/sack/loss)."""
    explosives = [e for e in plays if _is_explosive(e)]
    negatives = [e for e in plays if _is_negative(e)]

    exp_runs = [e for e in explosives if _is_run(e)]
    exp_passes = [e for e in explosives if _is_pass(e)]

    exp_yards = [e.yards_gained for e in explosives if e.yards_gained is not None]

    return {
        "explosive_count": len(explosives),
        "explosive_pct": round(len(explosives) / len(plays) * 100, 1) if plays else 0,
        "explosive_runs": len(exp_runs),
        "explosive_passes": len(exp_passes),
        "avg_explosive_gain": round(sum(exp_yards) / len(exp_yards), 1) if exp_yards else 0,
        "top_explosive_plays": dict(Counter(e.play_type for e in explosives if e.play_type).most_common(4)),
        "top_explosive_formations": dict(Counter(e.formation for e in explosives if e.formation).most_common(3)),
        "negative_count": len(negatives),
        "negative_pct": round(len(negatives) / len(plays) * 100, 1) if plays else 0,
        "top_negative_plays": dict(Counter(e.play_type for e in negatives if e.play_type).most_common(4)),
    }


def _personnel_detail(plays) -> Dict[str, Any]:
    """Personnel groups: count, run/pass split, avg yards, success rate."""
    by_personnel = defaultdict(list)
    for e in plays:
        if e.personnel:
            by_personnel[e.personnel].append(e)

    result = {}
    for p, pp in sorted(by_personnel.items(), key=lambda x: -len(x[1]))[:8]:
        runs = [x for x in pp if _is_run(x)]
        passes = [x for x in pp if _is_pass(x)]
        rp = len(runs) + len(passes)
        yards = [x.yards_gained for x in pp if x.yards_gained is not None]
        successes = [x for x in pp if _is_success(x)]
        result[p] = {
            "count": len(pp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(pp) * 100, 1) if pp else 0,
        }
    return result


def _pass_distribution(plays) -> Dict[str, Any]:
    """Pass distribution by target area — the field zone map every DB coach needs."""
    passes = [e for e in plays if _is_pass(e)]
    if not passes:
        return {"total": 0}

    by_area = defaultdict(list)
    for e in passes:
        area = _x(e, "target_area")
        if area:
            by_area[area].append(e)

    area_detail = {}
    for area, ap in sorted(by_area.items(), key=lambda x: -len(x[1])):
        yards = [e.yards_gained for e in ap if e.yards_gained is not None]
        successes = [e for e in ap if _is_success(e)]
        completions = [e for e in ap if (e.result or "").lower() in ("gain", "first down", "touchdown")]
        explosives = [e for e in ap if _is_explosive(e)]
        area_detail[area] = {
            "count": len(ap),
            "pct_of_passes": round(len(ap) / len(passes) * 100, 1) if passes else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(ap) * 100, 1) if ap else 0,
            "explosive_count": len(explosives),
        }

    # Group into field zones
    left_side = sum(len(by_area[k]) for k in by_area if "Left" in k)
    right_side = sum(len(by_area[k]) for k in by_area if "Right" in k)
    middle = sum(len(by_area[k]) for k in by_area if "Middle" in k or k in ("Post", "Go/Fly"))
    total_mapped = left_side + right_side + middle

    return {
        "total_passes": len(passes),
        "by_area": area_detail,
        "field_side_distribution": {
            "left_pct": round(left_side / total_mapped * 100, 1) if total_mapped else 0,
            "middle_pct": round(middle / total_mapped * 100, 1) if total_mapped else 0,
            "right_pct": round(right_side / total_mapped * 100, 1) if total_mapped else 0,
        },
        "hottest_area": max(area_detail, key=lambda k: area_detail[k]["count"]) if area_detail else None,
        "most_effective_area": max(area_detail, key=lambda k: area_detail[k]["avg_yards"]) if area_detail else None,
    }


def _run_gap_analysis(plays) -> Dict[str, Any]:
    """Specific gap targeting — what DL coaches need for alignment calls."""
    runs = [e for e in plays if _is_run(e)]
    if not runs:
        return {"total": 0}

    by_gap = defaultdict(list)
    for e in runs:
        gap = _x(e, "run_gap")
        if gap:
            by_gap[gap].append(e)

    gap_detail = {}
    for gap, gp in sorted(by_gap.items(), key=lambda x: -len(x[1])):
        yards = [e.yards_gained for e in gp if e.yards_gained is not None]
        successes = [e for e in gp if _is_success(e)]
        explosives = [e for e in gp if _is_explosive(e)]
        gap_detail[gap] = {
            "count": len(gp),
            "pct_of_runs": round(len(gp) / len(runs) * 100, 1) if runs else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(gp) * 100, 1) if gp else 0,
            "explosive_count": len(explosives),
        }

    return {
        "total_runs": len(runs),
        "by_gap": gap_detail,
        "most_targeted_gap": max(gap_detail, key=lambda k: gap_detail[k]["count"]) if gap_detail else None,
        "most_effective_gap": max(gap_detail, key=lambda k: gap_detail[k]["avg_yards"]) if gap_detail else None,
    }


def _motion_type_analysis(plays) -> Dict[str, Any]:
    """Motion type → play concept correlation — what each motion type signals."""
    motion_plays = [e for e in plays if e.motion]
    if not motion_plays:
        return {"total": 0}

    by_type = defaultdict(list)
    for e in motion_plays:
        mt = _x(e, "motion_type")
        if mt:
            by_type[mt].append(e)

    type_detail = {}
    for mt, mp in sorted(by_type.items(), key=lambda x: -len(x[1])):
        runs = [e for e in mp if _is_run(e)]
        passes = [e for e in mp if _is_pass(e)]
        rp = len(runs) + len(passes)
        yards = [e.yards_gained for e in mp if e.yards_gained is not None]
        top_concepts = Counter(
            _x(e, "run_concept") or _x(e, "pass_concept") for e in mp
            if _x(e, "run_concept") or _x(e, "pass_concept")
        )
        type_detail[mt] = {
            "count": len(mp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "top_concepts": dict(top_concepts.most_common(3)),
        }

    return {
        "total_motion_plays": len(motion_plays),
        "by_type": type_detail,
    }


def _safety_disguise_analysis(plays) -> Dict[str, Any]:
    """Pre-snap shell vs. post-snap rotation — does their secondary disguise or tip coverage?"""
    if not plays:
        return {"total": 0}

    matched = 0
    mismatched = 0
    shell_rotation_map = defaultdict(lambda: defaultdict(int))

    for e in plays:
        shell = _x(e, "coverage_shell")
        rotation = _x(e, "safety_rotation")
        if shell and rotation:
            shell_rotation_map[shell][rotation] += 1
            if shell == "Two-High" and rotation == "Stayed Two-High":
                matched += 1
            elif shell == "One-High" and rotation == "Rotated Single High":
                matched += 1
            elif shell == "Zero" and rotation == "Pressed Up":
                matched += 1
            else:
                mismatched += 1

    total_with_data = matched + mismatched
    disguise_rate = round(mismatched / total_with_data * 100, 1) if total_with_data else 0

    srm = {shell: dict(Counter(rots).most_common(4)) for shell, rots in shell_rotation_map.items()}

    corner_techniques = Counter(_x(e, "corner_technique") for e in plays if _x(e, "corner_technique"))
    lb_alignments = Counter(_x(e, "linebacker_alignment") for e in plays if _x(e, "linebacker_alignment"))

    return {
        "total_plays": len(plays),
        "disguise_rate": disguise_rate,
        "shell_to_rotation_map": srm,
        "corner_techniques": dict(corner_techniques.most_common(4)),
        "linebacker_alignments": dict(lb_alignments.most_common(4)),
    }


def _pressure_gap_analysis(plays) -> Dict[str, Any]:
    """WHERE the blitz/pressure comes from — OL protection slide intelligence."""
    blitz_plays = [e for e in plays if e.blitz and e.blitz.lower() not in ("", "none", "no")]
    if not blitz_plays:
        return {"total": 0}

    by_gap = defaultdict(list)
    for e in blitz_plays:
        gap = _x(e, "pressure_gap")
        if gap:
            by_gap[gap].append(e)

    gap_detail = {}
    for gap, gp in sorted(by_gap.items(), key=lambda x: -len(x[1])):
        yards = [e.yards_gained for e in gp if e.yards_gained is not None]
        sacks = [e for e in gp if (e.result or "").lower() == "sack"]
        explosives = [e for e in gp if _is_explosive(e)]
        gap_detail[gap] = {
            "count": len(gp),
            "pct_of_blitzes": round(len(gp) / len(blitz_plays) * 100, 1) if blitz_plays else 0,
            "avg_yards_allowed": round(sum(yards) / len(yards), 1) if yards else 0,
            "sacks": len(sacks),
            "explosives_allowed": len(explosives),
        }

    return {
        "total_blitzes": len(blitz_plays),
        "by_gap": gap_detail,
        "primary_pressure_gap": max(gap_detail, key=lambda k: gap_detail[k]["count"]) if gap_detail else None,
    }


def _tempo_analysis(plays) -> Dict[str, Any]:
    """No-huddle / hurry-up tendencies — when and how effective."""
    if not plays:
        return {"total": 0}

    by_tempo = defaultdict(list)
    for e in plays:
        t = _x(e, "tempo")
        if t:
            by_tempo[t].append(e)

    tempo_detail = {}
    for t, tp in sorted(by_tempo.items(), key=lambda x: -len(x[1])):
        runs = [e for e in tp if _is_run(e)]
        passes = [e for e in tp if _is_pass(e)]
        rp = len(runs) + len(passes)
        yards = [e.yards_gained for e in tp if e.yards_gained is not None]
        successes = [e for e in tp if _is_success(e)]
        tempo_detail[t] = {
            "count": len(tp),
            "pct": round(len(tp) / len(plays) * 100, 1) if plays else 0,
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(tp) * 100, 1) if tp else 0,
        }

    hurry_up_count = len(by_tempo.get("Hurry-Up", [])) + len(by_tempo.get("No-Huddle", []))
    return {
        "total_plays": len(plays),
        "no_huddle_hurry_count": hurry_up_count,
        "no_huddle_hurry_pct": round(hurry_up_count / len(plays) * 100, 1) if plays else 0,
        "by_tempo": tempo_detail,
    }


def _score_situation_analysis(plays) -> Dict[str, Any]:
    """Do their tendencies shift based on game script? Critical for understanding 'real' offense."""
    if not plays:
        return {"total": 0}

    by_situation = defaultdict(list)
    for e in plays:
        ss = _x(e, "score_situation")
        if ss:
            by_situation[ss].append(e)

    situation_detail = {}
    for ss, sp in sorted(by_situation.items(), key=lambda x: -len(x[1])):
        runs = [e for e in sp if _is_run(e)]
        passes = [e for e in sp if _is_pass(e)]
        rp = len(runs) + len(passes)
        yards = [e.yards_gained for e in sp if e.yards_gained is not None]
        top_plays = Counter(e.play_type for e in sp if e.play_type)
        situation_detail[ss] = {
            "count": len(sp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "top_plays": dict(top_plays.most_common(4)),
        }

    return {
        "total_plays_with_score_data": sum(len(v) for v in by_situation.values()),
        "by_situation": situation_detail,
    }


def _run_direction_analysis(plays) -> Dict[str, Any]:
    """Run direction breakdown: inside vs outside, left vs right, concept breakdown."""
    runs = [e for e in plays if _is_run(e)]
    if not runs:
        return {"total": 0}

    by_direction = defaultdict(list)
    for e in runs:
        d = _x(e, "run_direction")
        if d:
            by_direction[d].append(e)

    direction_detail = {}
    for direction, dp in sorted(by_direction.items(), key=lambda x: -len(x[1])):
        yards = [e.yards_gained for e in dp if e.yards_gained is not None]
        successes = [e for e in dp if _is_success(e)]
        explosives = [e for e in dp if _is_explosive(e)]
        direction_detail[direction] = {
            "count": len(dp),
            "pct_of_runs": round(len(dp) / len(runs) * 100, 1) if runs else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(dp) * 100, 1) if dp else 0,
            "explosive_count": len(explosives),
        }

    by_concept = Counter(_x(e, "run_concept") for e in runs if _x(e, "run_concept"))
    concept_detail = {}
    for concept, count in by_concept.most_common(8):
        cp = [e for e in runs if _x(e, "run_concept") == concept]
        yards = [e.yards_gained for e in cp if e.yards_gained is not None]
        successes = [e for e in cp if _is_success(e)]
        concept_detail[concept] = {
            "count": count,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(cp) * 100, 1) if cp else 0,
        }

    inside = [e for e in runs if "Inside" in (_x(e, "run_direction") or "")]
    outside = [e for e in runs if "Outside" in (_x(e, "run_direction") or "")]
    left = [e for e in runs if "Left" in (_x(e, "run_direction") or "")]
    right = [e for e in runs if "Right" in (_x(e, "run_direction") or "")]

    return {
        "total_runs": len(runs),
        "inside_pct": round(len(inside) / len(runs) * 100, 1) if runs else 0,
        "outside_pct": round(len(outside) / len(runs) * 100, 1) if runs else 0,
        "left_pct": round(len(left) / (len(left) + len(right)) * 100, 1) if (left or right) else 0,
        "right_pct": round(len(right) / (len(left) + len(right)) * 100, 1) if (left or right) else 0,
        "by_direction": direction_detail,
        "by_concept": concept_detail,
    }


def _pass_concept_analysis(plays) -> Dict[str, Any]:
    """Pass concept breakdown: concept type, depth, effectiveness."""
    passes = [e for e in plays if _is_pass(e)]
    if not passes:
        return {"total": 0}

    by_concept = Counter(_x(e, "pass_concept") for e in passes if _x(e, "pass_concept"))
    concept_detail = {}
    for concept, count in by_concept.most_common(10):
        cp = [e for e in passes if _x(e, "pass_concept") == concept]
        yards = [e.yards_gained for e in cp if e.yards_gained is not None]
        completions = [e for e in cp if (e.result or "").lower() in ("gain", "first down", "touchdown")]
        successes = [e for e in cp if _is_success(e)]
        explosives = [e for e in cp if _is_explosive(e)]
        concept_detail[concept] = {
            "count": count,
            "pct_of_passes": round(count / len(passes) * 100, 1) if passes else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(cp) * 100, 1) if cp else 0,
            "explosive_count": len(explosives),
        }

    by_depth = Counter(_x(e, "pass_depth") for e in passes if _x(e, "pass_depth"))
    depth_detail = {}
    for depth, count in by_depth.most_common(6):
        dp = [e for e in passes if _x(e, "pass_depth") == depth]
        yards = [e.yards_gained for e in dp if e.yards_gained is not None]
        successes = [e for e in dp if _is_success(e)]
        depth_detail[depth] = {
            "count": count,
            "pct_of_passes": round(count / len(passes) * 100, 1) if passes else 0,
            "avg_yards": round(sum(yards) / len(yards), 1) if yards else 0,
            "success_rate": round(len(successes) / len(dp) * 100, 1) if dp else 0,
        }

    return {
        "total_passes": len(passes),
        "by_concept": concept_detail,
        "by_depth": depth_detail,
    }


def _defensive_shell_analysis(plays) -> Dict[str, Any]:
    """Pre-snap shell + post-snap coverage + pressure type breakdown."""
    if not plays:
        return {"total": 0}

    shells = Counter(_x(e, "coverage_shell") for e in plays if _x(e, "coverage_shell"))
    pressure_types = Counter(_x(e, "pressure_type") for e in plays if _x(e, "pressure_type"))

    # Shell to coverage mapping: what do they actually run out of each shell?
    shell_to_coverage = defaultdict(list)
    for e in plays:
        shell = _x(e, "coverage_shell")
        if shell and e.coverage:
            shell_to_coverage[shell].append(e.coverage)

    shell_coverage_map = {
        shell: dict(Counter(covs).most_common(4))
        for shell, covs in shell_to_coverage.items()
    }

    # Pressure type breakdown: 4-man vs 5-man vs 6-man+
    pressure_results = {}
    for pt, count in pressure_types.most_common(6):
        pp = [e for e in plays if _x(e, "pressure_type") == pt]
        blitzes = [e for e in pp if e.blitz and e.blitz.lower() not in ("", "none", "no")]
        yards = [e.yards_gained for e in pp if e.yards_gained is not None]
        explosives = [e for e in pp if _is_explosive(e)]
        pressure_results[pt] = {
            "count": count,
            "avg_yards_allowed": round(sum(yards) / len(yards), 1) if yards else 0,
            "explosive_allowed": len(explosives),
        }

    return {
        "total_plays": len(plays),
        "coverage_shells": dict(shells.most_common(4)),
        "shell_to_coverage_map": shell_coverage_map,
        "pressure_types": dict(pressure_types.most_common(6)),
        "pressure_detail": pressure_results,
    }


def _opening_plays(plays) -> Dict[str, Any]:
    """Drive-opening tendencies: 1st & 10 from own territory."""
    openers = [
        e for e in plays
        if e.down == 1 and e.distance == 10
        and e.field_position and _is_own_territory(e.field_position)
    ]
    if not openers:
        return {"total": 0}

    runs = [e for e in openers if _is_run(e)]
    passes = [e for e in openers if _is_pass(e)]
    rp = len(runs) + len(passes)
    return {
        "total": len(openers),
        "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
        "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
        "top_plays": dict(Counter(e.play_type for e in openers if e.play_type).most_common(4)),
        "top_formations": dict(Counter(e.formation for e in openers if e.formation).most_common(3)),
    }


def _short_yardage_detail(plays) -> Dict[str, Any]:
    """3rd & short + 4th & short: what do they call, success rate."""
    sy = [e for e in plays if e.down in (3, 4) and e.distance and e.distance <= 3]
    if not sy:
        return {"total": 0}

    runs = [e for e in sy if _is_run(e)]
    passes = [e for e in sy if _is_pass(e)]
    rp = len(runs) + len(passes)
    successes = [e for e in sy if _is_success(e)]

    by_down = {}
    for down in (3, 4):
        dp = [e for e in sy if e.down == down]
        if dp:
            d_runs = [e for e in dp if _is_run(e)]
            d_passes = [e for e in dp if _is_pass(e)]
            d_rp = len(d_runs) + len(d_passes)
            d_succ = [e for e in dp if _is_success(e)]
            by_down[f"down_{down}"] = {
                "total": len(dp),
                "run_pct": round(len(d_runs) / d_rp * 100, 1) if d_rp else 0,
                "pass_pct": round(len(d_passes) / d_rp * 100, 1) if d_rp else 0,
                "success_rate": round(len(d_succ) / len(dp) * 100, 1) if dp else 0,
                "top_plays": dict(Counter(e.play_type for e in dp if e.play_type).most_common(3)),
            }

    return {
        "total": len(sy),
        "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
        "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
        "success_rate": round(len(successes) / len(sy) * 100, 1) if sy else 0,
        "top_plays": dict(Counter(e.play_type for e in sy if e.play_type).most_common(5)),
        "by_down": by_down,
    }


def _play_action_analysis(plays) -> Dict[str, Any]:
    """Play action rate vs pure dropback — yards, success rate, top formations and fakes."""
    passes = [e for e in plays if _is_pass(e)]
    if not passes:
        return {"total_pa": 0, "pa_rate": 0}

    def _is_pa(e) -> bool:
        pt = (e.play_type or "").lower()
        if "play" in pt and "action" in pt:
            return True
        if "play-action" in pt or pt == "pa":
            return True
        if _x(e, "run_concept") is not None and _is_pass(e):
            return True
        if _x(e, "is_play_action") is True:
            return True
        return False

    pa_passes = [e for e in passes if _is_pa(e)]
    pure_dropback = [e for e in passes if not _is_pa(e)]

    def _avg_yards(lst):
        ys = [e.yards_gained for e in lst if e.yards_gained is not None]
        return round(sum(ys) / len(ys), 1) if ys else 0

    def _success_rate(lst):
        return round(sum(1 for e in lst if _is_success(e)) / len(lst) * 100, 1) if lst else 0

    pa_formations = Counter(e.formation for e in pa_passes if e.formation)
    pa_concepts = Counter(
        (_x(e, "run_concept") or e.play_type) for e in pa_passes
        if (_x(e, "run_concept") or e.play_type)
    )

    return {
        "total_pa": len(pa_passes),
        "pa_rate": round(len(pa_passes) / len(passes) * 100, 1) if passes else 0,
        "pa_avg_yards": _avg_yards(pa_passes),
        "dropback_avg_yards": _avg_yards(pure_dropback),
        "pa_success_rate": _success_rate(pa_passes),
        "dropback_success_rate": _success_rate(pure_dropback),
        "top_pa_formations": dict(pa_formations.most_common(5)),
        "top_pa_fake_concepts": dict(pa_concepts.most_common(5)),
    }


def _screen_game_analysis(plays) -> Dict[str, Any]:
    """Screen pass analysis by sub-type, down, and personnel."""
    passes = [e for e in plays if _is_pass(e)]
    if not passes:
        return {"total_screens": 0, "screen_rate": 0}

    SCREEN_CONCEPTS = {"Screen", "Bubble", "Slip Screen", "RB Screen", "WR Screen",
                       "TE Screen", "Tunnel Screen", "Bubble Screen"}

    def _is_screen(e) -> bool:
        pt = (e.play_type or "").lower()
        if "screen" in pt or "bubble" in pt:
            return True
        concept = _x(e, "pass_concept") or _x(e, "screen_subtype") or ""
        return concept in SCREEN_CONCEPTS

    screens = [e for e in passes if _is_screen(e)]
    if not screens:
        return {"total_screens": 0, "screen_rate": 0}

    def _subtype(e):
        st = _x(e, "screen_subtype")
        if st:
            return st
        concept = _x(e, "pass_concept") or ""
        if concept in SCREEN_CONCEPTS:
            return concept
        pt = (e.play_type or "").lower()
        if "bubble" in pt:
            return "Bubble Screen"
        if "slip" in pt:
            return "Slip Screen"
        if "tunnel" in pt:
            return "Tunnel Screen"
        return "Screen"

    by_subtype = defaultdict(lambda: {"count": 0, "yards": [], "success": 0, "explosive": 0})
    for e in screens:
        st = _subtype(e)
        by_subtype[st]["count"] += 1
        if e.yards_gained is not None:
            by_subtype[st]["yards"].append(e.yards_gained)
        if _is_success(e):
            by_subtype[st]["success"] += 1
        if _is_explosive(e):
            by_subtype[st]["explosive"] += 1

    subtype_summary = {}
    for st, d in by_subtype.items():
        ys = d["yards"]
        subtype_summary[st] = {
            "count": d["count"],
            "avg_yards": round(sum(ys) / len(ys), 1) if ys else 0,
            "success_rate": round(d["success"] / d["count"] * 100, 1) if d["count"] else 0,
            "explosive": d["explosive"],
        }

    return {
        "total_screens": len(screens),
        "screen_rate": round(len(screens) / len(passes) * 100, 1),
        "by_subtype": subtype_summary,
        "by_down": dict(Counter(e.down for e in screens if e.down)),
        "by_personnel": dict(Counter(e.personnel for e in screens if e.personnel).most_common(6)),
    }


def _goal_line_analysis(plays) -> Dict[str, Any]:
    """OPP 5 and in — tightest red zone, highest leverage plays."""
    gl = []
    for e in plays:
        fp = (e.field_position or "")
        parts = fp.split()
        try:
            if len(parts) >= 2 and parts[0].upper() == "OPP" and int(parts[1]) <= 5:
                gl.append(e)
                continue
        except (ValueError, IndexError):
            pass
        if _x(e, "goal_line") is True:
            gl.append(e)

    if not gl:
        return {"total_plays": 0}

    runs = [e for e in gl if _is_run(e)]
    passes = [e for e in gl if _is_pass(e)]
    scoring = [e for e in gl if (e.result or "").lower() in ("touchdown", "td")]
    success = [e for e in gl if _is_success(e)]

    return {
        "total_plays": len(gl),
        "run_pct": round(len(runs) / len(gl) * 100, 1) if gl else 0,
        "pass_pct": round(len(passes) / len(gl) * 100, 1) if gl else 0,
        "top_formations": dict(Counter(e.formation for e in gl if e.formation).most_common(5)),
        "top_play_types": dict(Counter(e.play_type for e in gl if e.play_type).most_common(5)),
        "personnel_distribution": dict(Counter(e.personnel for e in gl if e.personnel).most_common(5)),
        "scoring_plays": len(scoring),
        "scoring_rate": round(len(scoring) / len(gl) * 100, 1) if gl else 0,
        "success_rate": round(len(success) / len(gl) * 100, 1) if gl else 0,
    }


def _fourth_down_analysis(plays) -> Dict[str, Any]:
    """4th down go-for-it analysis by field position zone."""
    fourth = [e for e in plays if e.down == 4]
    if not fourth:
        return {"total": 0}

    own = [e for e in fourth if (e.field_position or "").upper().startswith("OWN")]
    opp = [e for e in fourth if (e.field_position or "").upper().startswith("OPP")]
    success = [e for e in fourth if _is_success(e)]
    distances = [e.distance for e in fourth if e.distance is not None]

    def _zone_summary(zone_plays):
        if not zone_plays:
            return {"total": 0}
        s = [e for e in zone_plays if _is_success(e)]
        return {
            "total": len(zone_plays),
            "success_rate": round(len(s) / len(zone_plays) * 100, 1),
            "top_formations": dict(Counter(e.formation for e in zone_plays if e.formation).most_common(4)),
            "top_plays": dict(Counter(e.play_type for e in zone_plays if e.play_type).most_common(4)),
            "avg_distance": round(
                sum(e.distance for e in zone_plays if e.distance) / len([e for e in zone_plays if e.distance]), 1
            ) if any(e.distance for e in zone_plays) else 0,
        }

    return {
        "total": len(fourth),
        "success_rate": round(len(success) / len(fourth) * 100, 1),
        "avg_distance": round(sum(distances) / len(distances), 1) if distances else 0,
        "own_territory": _zone_summary(own),
        "opp_territory": _zone_summary(opp),
    }


def _third_down_by_distance(plays) -> Dict[str, Any]:
    """3rd down split into 4 buckets: short, manageable, medium, long."""
    third = [e for e in plays if e.down == 3]
    if not third:
        return {}

    buckets = {
        "short_1_2": [e for e in third if e.distance and e.distance <= 2],
        "manageable_3_5": [e for e in third if e.distance and 3 <= e.distance <= 5],
        "medium_6_8": [e for e in third if e.distance and 6 <= e.distance <= 8],
        "long_9_plus": [e for e in third if e.distance and e.distance >= 9],
    }

    def _bucket(bp):
        if not bp:
            return {"total": 0}
        runs = [e for e in bp if _is_run(e)]
        passes = [e for e in bp if _is_pass(e)]
        rp = len(runs) + len(passes)
        success = [e for e in bp if _is_success(e)]
        top_concepts = Counter(
            _x(e, "pass_concept") or e.play_type for e in passes
            if (_x(e, "pass_concept") or e.play_type)
        )
        return {
            "total": len(bp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "conversion_rate": round(len(success) / len(bp) * 100, 1),
            "top_pass_concepts": dict(top_concepts.most_common(5)),
            "top_formations": dict(Counter(e.formation for e in bp if e.formation).most_common(4)),
        }

    return {k: _bucket(v) for k, v in buckets.items()}


def _two_minute_drill(plays) -> Dict[str, Any]:
    """Late-game hurry-up / trailing-score tendencies."""
    two_min = [
        e for e in plays
        if (_x(e, "tempo") or "").lower() in ("hurry up", "hurry-up", "hurry", "no-huddle", "no huddle")
        or (_x(e, "score_situation") or "") in ("Trailing 1-7", "Trailing 8+")
    ]
    if not two_min:
        return {"total": 0}

    runs = [e for e in two_min if _is_run(e)]
    passes = [e for e in two_min if _is_pass(e)]
    rp = len(runs) + len(passes)
    success = [e for e in two_min if _is_success(e)]
    explosive = [e for e in two_min if _is_explosive(e)]
    no_huddle = [e for e in two_min if (_x(e, "tempo") or "").lower() in ("no-huddle", "no huddle")]
    concepts = Counter(
        _x(e, "pass_concept") or e.play_type for e in passes if (_x(e, "pass_concept") or e.play_type)
    )

    return {
        "total": len(two_min),
        "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
        "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
        "success_rate": round(len(success) / len(two_min) * 100, 1) if two_min else 0,
        "explosive_count": len(explosive),
        "no_huddle_rate": round(len(no_huddle) / len(two_min) * 100, 1) if two_min else 0,
        "pass_concept_distribution": dict(concepts.most_common(8)),
    }


def _pre_snap_tell_matrix(plays) -> list:
    """Formation + motion + down + distance bucket → play prediction (top 10 combos, count >= 3)."""
    def _dist_bucket(distance):
        if distance is None:
            return "Unknown"
        if distance <= 3:
            return "Short (1-3)"
        if distance <= 7:
            return "Medium (4-7)"
        return "Long (8+)"

    combos = defaultdict(lambda: {"runs": 0, "passes": 0, "concepts": [], "total": 0})
    for e in plays:
        if not (e.formation and e.down):
            continue
        key = (e.formation, bool(e.motion), e.down, _dist_bucket(e.distance))
        combos[key]["total"] += 1
        if _is_run(e):
            combos[key]["runs"] += 1
        elif _is_pass(e):
            combos[key]["passes"] += 1
        concept = _x(e, "pass_concept") or e.play_type
        if concept:
            combos[key]["concepts"].append(concept)

    result = []
    for (formation, motion, down, dist_bucket), d in combos.items():
        if d["total"] < 3:
            continue
        rp = d["runs"] + d["passes"]
        most_common = Counter(d["concepts"]).most_common(1)
        result.append({
            "formation": formation,
            "motion": motion,
            "down": down,
            "distance_bucket": dist_bucket,
            "count": d["total"],
            "run_pct": round(d["runs"] / rp * 100, 1) if rp else 0,
            "pass_pct": round(d["passes"] / rp * 100, 1) if rp else 0,
            "most_common_concept": most_common[0][0] if most_common else None,
        })

    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:10]


def analyze_football(events) -> Dict[str, Any]:
    plays = [e for e in events if _is_play(e)]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    runs = [e for e in plays if _is_run(e)]
    passes = [e for e in plays if _is_pass(e)]

    rp_total = len(runs) + len(passes)
    run_pct = round(len(runs) / rp_total * 100, 1) if rp_total else 0
    pass_pct = round(len(passes) / rp_total * 100, 1) if rp_total else 0

    # Overall success rate and explosiveness
    successes = [e for e in plays if _is_success(e)]
    overall_success_rate = round(len(successes) / total * 100, 1) if total else 0
    explosives = [e for e in plays if _is_explosive(e)]
    negatives = [e for e in plays if _is_negative(e)]

    yards_all = [e.yards_gained for e in plays if e.yards_gained is not None]
    run_yards = [e.yards_gained for e in runs if e.yards_gained is not None]
    pass_yards = [e.yards_gained for e in passes if e.yards_gained is not None]

    personnel = Counter(e.personnel for e in plays if e.personnel)
    results = Counter(e.result for e in plays if e.result)

    return {
        "total_plays": total,
        "run_plays": len(runs),
        "pass_plays": len(passes),
        "run_pass_ratio": {"run_pct": run_pct, "pass_pct": pass_pct},
        "overall_success_rate": overall_success_rate,
        "avg_yards_per_play": round(sum(yards_all) / len(yards_all), 1) if yards_all else 0,
        "avg_yards_per_run": round(sum(run_yards) / len(run_yards), 1) if run_yards else 0,
        "avg_yards_per_pass": round(sum(pass_yards) / len(pass_yards), 1) if pass_yards else 0,

        # Down & Distance (detailed)
        "first_down": _down_summary([e for e in plays if e.down == 1]),
        "second_long": _down_summary([e for e in plays if e.down == 2 and e.distance and e.distance >= 7]),
        "second_medium": _down_summary([e for e in plays if e.down == 2 and e.distance and 4 <= e.distance <= 6]),
        "second_short": _down_summary([e for e in plays if e.down == 2 and e.distance and e.distance <= 3]),
        "third_long": _down_summary([e for e in plays if e.down == 3 and e.distance and e.distance >= 7]),
        "third_medium": _down_summary([e for e in plays if e.down == 3 and e.distance and 4 <= e.distance <= 6]),
        "third_short": _down_summary([e for e in plays if e.down == 3 and e.distance and e.distance <= 3]),
        "fourth_down": _down_summary([e for e in plays if e.down == 4]),

        # Formation intelligence
        "top_formations": dict(Counter(e.formation for e in plays if e.formation).most_common(10)),
        "formation_play_matrix": _formation_play_matrix(plays),

        # Play type intelligence
        "play_type_mix": dict(Counter(e.play_type for e in plays if e.play_type).most_common(12)),
        "yards_by_play_type": _yards_by_play_type(plays),

        # Hash + field position
        "hash_play_matrix": _hash_play_matrix(plays),

        # Situational
        "short_yardage": _short_yardage_detail(plays),
        "red_zone": _red_zone_detail(plays),
        "opening_plays": _opening_plays(plays),

        # Personnel
        "personnel_usage": dict(personnel.most_common(8)),
        "personnel_detail": _personnel_detail(plays),

        # Motion
        "motion_analysis": _motion_analysis(plays),

        # Explosive / negative
        "explosive_negative": _explosive_negative_analysis(plays),

        # Deep extraction — run
        "run_direction_analysis": _run_direction_analysis(plays),
        "run_gap_analysis": _run_gap_analysis(plays),

        # Deep extraction — pass
        "pass_concept_analysis": _pass_concept_analysis(plays),
        "pass_distribution": _pass_distribution(plays),

        # Deep extraction — motion and tempo
        "motion_type_analysis": _motion_type_analysis(plays),
        "tempo_analysis": _tempo_analysis(plays),

        # Game script
        "score_situation_analysis": _score_situation_analysis(plays),

        # Play results
        "play_results": dict(results.most_common(10)),

        # Moat analysis — advanced
        "play_action": _play_action_analysis(plays),
        "screen_game": _screen_game_analysis(plays),
        "goal_line": _goal_line_analysis(plays),
        "fourth_down_deep": _fourth_down_analysis(plays),
        "third_down_by_distance": _third_down_by_distance(plays),
        "two_minute_drill": _two_minute_drill(plays),
        "pre_snap_tells": _pre_snap_tell_matrix(plays),
    }


def analyze_football_defense(events) -> Dict[str, Any]:
    """Defensive tendencies for the scouted team's defense."""
    plays = [e for e in events if _is_play(e)]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    fronts = Counter(e.defensive_front for e in plays if e.defensive_front)
    coverages = Counter(e.coverage for e in plays if e.coverage)
    blitzes = [e for e in plays if e.blitz and e.blitz.lower() not in ("", "none", "no")]
    blitz_pct = round(len(blitzes) / total * 100, 1) if total else 0
    blitz_types = Counter(e.blitz for e in blitzes if e.blitz)

    # Coverage by down + distance
    coverage_by_down = {}
    for down in (1, 2, 3, 4):
        dp = [e for e in plays if e.down == down]
        if dp:
            cov = Counter(p.coverage for p in dp if p.coverage)
            blitz_dp = [p for p in dp if p.blitz and p.blitz.lower() not in ("", "none", "no")]
            coverage_by_down[f"down_{down}"] = {
                "total": len(dp),
                "coverages": dict(cov.most_common(4)),
                "blitz_pct": round(len(blitz_dp) / len(dp) * 100, 1) if dp else 0,
            }

    # Blitz by down+distance buckets
    def _blitz_bucket(down, min_dist=None, max_dist=None):
        dp = [e for e in plays if e.down == down]
        if min_dist is not None:
            dp = [e for e in dp if e.distance and e.distance >= min_dist]
        if max_dist is not None:
            dp = [e for e in dp if e.distance and e.distance <= max_dist]
        blitz_dp = [e for e in dp if e in blitzes]
        return {
            "total": len(dp),
            "blitz_pct": round(len(blitz_dp) / len(dp) * 100, 1) if dp else 0,
            "top_coverages": dict(Counter(e.coverage for e in dp if e.coverage).most_common(3)),
        }

    blitz_by_situation = {
        "3rd_long_6plus": _blitz_bucket(3, min_dist=6),
        "3rd_medium_4to5": _blitz_bucket(3, min_dist=4, max_dist=5),
        "3rd_short_1to3": _blitz_bucket(3, max_dist=3),
        "2nd_long_7plus": _blitz_bucket(2, min_dist=7),
        "1st_and_10": _blitz_bucket(1),
    }

    # Front + coverage pairings
    pairing_counter = Counter()
    for e in plays:
        if e.defensive_front and e.coverage:
            pairing_counter[(e.defensive_front, e.coverage)] += 1
    top_pairings = [
        {"front": k[0], "coverage": k[1], "count": v}
        for k, v in pairing_counter.most_common(8)
    ]

    # Coverage vs offensive formation (if formation data exists on defensive plays)
    coverage_vs_formation = defaultdict(lambda: defaultdict(int))
    for e in plays:
        if e.formation and e.coverage:
            coverage_vs_formation[e.formation][e.coverage] += 1
    cvf = {
        form: dict(Counter(covs).most_common(3))
        for form, covs in sorted(coverage_vs_formation.items(), key=lambda x: -sum(x[1].values()))[:8]
    }

    # Red zone defense
    rz_plays = [e for e in plays if e.field_position and _is_red_zone(e.field_position)]
    rz_detail = {}
    if rz_plays:
        rz_fronts = Counter(e.defensive_front for e in rz_plays if e.defensive_front)
        rz_coverages = Counter(e.coverage for e in rz_plays if e.coverage)
        rz_blitz = [e for e in rz_plays if e.blitz and e.blitz.lower() not in ("", "none", "no")]
        rz_detail = {
            "total": len(rz_plays),
            "top_fronts": dict(rz_fronts.most_common(4)),
            "top_coverages": dict(rz_coverages.most_common(4)),
            "blitz_pct": round(len(rz_blitz) / len(rz_plays) * 100, 1) if rz_plays else 0,
        }

    # Pressure results: when they blitz, what happens
    blitz_results = Counter(e.result for e in blitzes if e.result)
    blitz_yards = [e.yards_gained for e in blitzes if e.yards_gained is not None]
    pressure_results = {
        "results": dict(blitz_results.most_common(6)),
        "avg_yards_allowed": round(sum(blitz_yards) / len(blitz_yards), 1) if blitz_yards else 0,
        "explosives_allowed": len([e for e in blitzes if _is_explosive(e)]),
    }

    results = Counter(e.result for e in plays if e.result)

    return {
        "total_plays": total,
        "top_fronts": dict(fronts.most_common(8)),
        "top_coverages": dict(coverages.most_common(8)),
        "blitz_pct": blitz_pct,
        "blitz_types": dict(blitz_types.most_common(8)),
        "coverage_by_down": coverage_by_down,
        "blitz_by_situation": blitz_by_situation,
        "top_front_coverage_pairings": top_pairings,
        "coverage_vs_formation_faced": cvf,
        "red_zone_defense": rz_detail,
        "pressure_results": pressure_results,
        "play_results": dict(results.most_common(10)),

        # Deep extraction — coverage, disguise, pressure
        "defensive_shell_analysis": _defensive_shell_analysis(plays),
        "safety_disguise_analysis": _safety_disguise_analysis(plays),
        "pressure_gap_analysis": _pressure_gap_analysis(plays),
    }


def analyze_football_special(events) -> Dict[str, Any]:
    """Special teams tendencies (punt, kickoff, FG/PAT, returns)."""
    plays = [e for e in events if _is_play(e)]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    units = Counter(e.play_type for e in plays if e.play_type)
    results = Counter(e.result for e in plays if e.result)
    formations = Counter(e.formation for e in plays if e.formation)

    def _unit(name_set):
        return [e for e in plays if (e.play_type or "").lower() in name_set]

    fg = _unit({"field goal", "fg"})
    fg_made = [e for e in fg if (e.result or "").lower() in ("made", "good")]
    fg_yards = [e.yards_gained for e in fg if e.yards_gained is not None]

    pat = _unit({"pat", "extra point"})
    punts = _unit({"punt"})
    punt_yards = [e.yards_gained for e in punts if e.yards_gained is not None]
    kickoffs = _unit({"kickoff", "ko"})
    returns = _unit({"punt return", "kick return", "kickoff return", "return"})
    return_yards = [e.yards_gained for e in returns if e.yards_gained is not None]
    trick = [e for e in plays if (e.play_type or "").lower() in ("fake punt", "fake field goal", "onside kick", "trick") or (e.result or "").lower() in ("fake", "onside")]

    # Breakdown: FG range
    fg_by_range = {"inside_30": 0, "30_39": 0, "40_49": 0, "50_plus": 0}
    for e in fg:
        if e.yards_gained is not None:
            if e.yards_gained < 30:
                fg_by_range["inside_30"] += 1
            elif e.yards_gained < 40:
                fg_by_range["30_39"] += 1
            elif e.yards_gained < 50:
                fg_by_range["40_49"] += 1
            else:
                fg_by_range["50_plus"] += 1

    return {
        "total_plays": total,
        "units": dict(units.most_common(12)),
        "formations": dict(formations.most_common(8)),
        "field_goals": {
            "attempts": len(fg),
            "made": len(fg_made),
            "fg_pct": round(len(fg_made) / len(fg) * 100, 1) if fg else 0,
            "avg_distance": round(sum(fg_yards) / len(fg_yards), 1) if fg_yards else 0,
            "by_range": fg_by_range,
        },
        "pat": {"attempts": len(pat)},
        "punts": {
            "count": len(punts),
            "avg_yards": round(sum(punt_yards) / len(punt_yards), 1) if punt_yards else 0,
        },
        "kickoffs": len(kickoffs),
        "returns": {
            "count": len(returns),
            "avg_yards": round(sum(return_yards) / len(return_yards), 1) if return_yards else 0,
            "explosive_returns": len([e for e in returns if (e.yards_gained or 0) >= 25]),
        },
        "trick_or_special": {
            "count": len(trick),
            "plays": [{"type": e.play_type, "result": e.result} for e in trick[:5]],
        },
        "play_results": dict(results.most_common(10)),
    }


def _is_red_zone(field_position: str) -> bool:
    try:
        parts = field_position.split()
        if len(parts) >= 2 and parts[0].upper() == "OPP":
            return int(parts[1]) <= 20
    except Exception:
        pass
    return False


def _is_own_territory(field_position: str) -> bool:
    try:
        parts = field_position.split()
        if len(parts) >= 2 and parts[0].upper() == "OWN":
            return True
    except Exception:
        pass
    return False
