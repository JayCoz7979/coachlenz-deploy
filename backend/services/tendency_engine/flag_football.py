from typing import List, Dict, Any
from collections import Counter, defaultdict
from .football import _x, _is_success, _is_explosive, _is_negative, _is_run, _is_pass, _kind, _down_summary


def _is_success_flag(e) -> bool:
    """Flag football success: looser thresholds — pass-dominant sport."""
    yards = e.yards_gained
    if yards is None:
        return False
    down = e.down
    distance = e.distance
    if down == 1:
        return yards > 0
    elif down == 2:
        return distance is not None and yards >= distance * 0.5
    elif down in (3, 4):
        return distance is not None and yards >= distance
    return yards > 0


def _route_analysis(passes) -> Dict[str, Any]:
    """Per route/play_type: attempts, completions, avg yards, explosive, pct_of_passes."""
    total = len(passes)
    if not total:
        return {}
    route_data = defaultdict(lambda: {"attempts": 0, "completions": 0, "yards": [], "explosive": 0})
    for e in passes:
        route = e.play_type or "Unknown"
        route_data[route]["attempts"] += 1
        result = (e.result or "").lower()
        if result in ("gain", "touchdown", "td", "first down"):
            route_data[route]["completions"] += 1
        yards = e.yards_gained
        if yards is not None:
            route_data[route]["yards"].append(yards)
        if yards is not None and yards >= 15:
            route_data[route]["explosive"] += 1

    out = []
    for route, d in route_data.items():
        ys = d["yards"]
        out.append({
            "route": route,
            "attempts": d["attempts"],
            "completions": d["completions"],
            "avg_yards": round(sum(ys) / len(ys), 1) if ys else 0,
            "explosive": d["explosive"],
            "pct_of_passes": round(d["attempts"] / total * 100, 1),
        })
    out.sort(key=lambda x: x["attempts"], reverse=True)
    return {"routes": out, "total_passes": total}


def _receiver_zone_targeting(passes) -> Dict[str, Any]:
    """Per zone: attempts, completion rate, avg yards, explosive. Groups into left/right/middle."""
    if not passes:
        return {}
    zones = defaultdict(lambda: {"attempts": 0, "completions": 0, "yards": [], "explosive": 0})
    for e in passes:
        raw_zone = (_x(e, "target_area") or "").lower()
        if "left" in raw_zone:
            zone = "left"
        elif "right" in raw_zone:
            zone = "right"
        elif "middle" in raw_zone or "center" in raw_zone:
            zone = "middle"
        else:
            zone = "unknown"
        zones[zone]["attempts"] += 1
        result = (e.result or "").lower()
        if result in ("gain", "touchdown", "td", "first down"):
            zones[zone]["completions"] += 1
        yards = e.yards_gained
        if yards is not None:
            zones[zone]["yards"].append(yards)
        if yards is not None and yards >= 15:
            zones[zone]["explosive"] += 1

    out = {}
    for zone, d in zones.items():
        ys = d["yards"]
        comp_rate = round(d["completions"] / d["attempts"] * 100, 1) if d["attempts"] else 0
        out[zone] = {
            "attempts": d["attempts"],
            "completion_rate": comp_rate,
            "avg_yards": round(sum(ys) / len(ys), 1) if ys else 0,
            "explosive": d["explosive"],
        }
    most_targeted = max(out, key=lambda z: out[z]["attempts"]) if out else None
    hottest = max(out, key=lambda z: out[z]["avg_yards"]) if out else None
    return {"by_zone": out, "most_targeted_zone": most_targeted, "hottest_zone": hottest}


def _scramble_analysis(plays) -> Dict[str, Any]:
    """QB scrambles = runs in flag football. Per direction, stats and success."""
    total = len(plays)
    runs = [e for e in plays if _is_run(e)]
    if not runs:
        return {"scramble_count": 0, "scramble_rate": 0}
    dirs = defaultdict(lambda: {"count": 0, "yards": [], "success": 0, "explosive": 0})
    for e in runs:
        direction = (_x(e, "run_direction") or "").lower()
        if "left" in direction:
            d = "left"
        elif "right" in direction:
            d = "right"
        elif "middle" in direction or "center" in direction:
            d = "middle"
        else:
            d = "unknown"
        dirs[d]["count"] += 1
        yards = e.yards_gained
        if yards is not None:
            dirs[d]["yards"].append(yards)
        if _is_success_flag(e):
            dirs[d]["success"] += 1
        if yards is not None and yards >= 10:
            dirs[d]["explosive"] += 1

    by_dir = {}
    for d, data in dirs.items():
        ys = data["yards"]
        by_dir[d] = {
            "count": data["count"],
            "avg_yards": round(sum(ys) / len(ys), 1) if ys else 0,
            "success_rate": round(data["success"] / data["count"] * 100, 1) if data["count"] else 0,
            "explosive": data["explosive"],
        }
    most_dangerous = max(by_dir, key=lambda d: by_dir[d]["avg_yards"]) if by_dir else None
    return {
        "scramble_count": len(runs),
        "scramble_rate": round(len(runs) / total * 100, 1) if total else 0,
        "by_direction": by_dir,
        "most_dangerous_direction": most_dangerous,
    }


def _flag_end_zone(plays) -> Dict[str, Any]:
    """OPP 10 and in analysis — red zone equivalent for flag."""
    end_zone = []
    for e in plays:
        fp = (e.field_position or "")
        parts = fp.split()
        try:
            if len(parts) >= 2 and parts[0].upper() == "OPP" and int(parts[1]) <= 10:
                end_zone.append(e)
        except (ValueError, IndexError):
            pass
    if not end_zone:
        return {"total_plays": 0}
    runs = [e for e in end_zone if _is_run(e)]
    passes = [e for e in end_zone if _is_pass(e)]
    scoring = [e for e in end_zone if (e.result or "").lower() in ("touchdown", "td")]
    top_formations = Counter(e.formation for e in end_zone if e.formation)
    top_routes = Counter(e.play_type for e in end_zone if e.play_type)
    success = [e for e in end_zone if _is_success_flag(e)]
    return {
        "total_plays": len(end_zone),
        "run_count": len(runs),
        "pass_count": len(passes),
        "run_pct": round(len(runs) / len(end_zone) * 100, 1) if end_zone else 0,
        "pass_pct": round(len(passes) / len(end_zone) * 100, 1) if end_zone else 0,
        "top_formations": dict(top_formations.most_common(5)),
        "top_routes": dict(top_routes.most_common(5)),
        "success_rate": round(len(success) / len(end_zone) * 100, 1) if end_zone else 0,
        "scoring_plays": len(scoring),
        "scoring_rate": round(len(scoring) / len(end_zone) * 100, 1) if end_zone else 0,
    }


def _flag_motion_analysis(plays) -> Dict[str, Any]:
    """Motion plays: per motion_type, run/pass split, top concepts, avg yards."""
    motion_plays = [e for e in plays if e.motion]
    no_motion = [e for e in plays if not e.motion]
    total = len(plays)
    if not total:
        return {}

    motion_pct = round(len(motion_plays) / total * 100, 1)
    motion_success = [e for e in motion_plays if _is_success_flag(e)]
    no_motion_success = [e for e in no_motion if _is_success_flag(e)]

    by_type = defaultdict(lambda: {"count": 0, "runs": 0, "passes": 0, "yards": [], "concepts": []})
    for e in motion_plays:
        mt = _x(e, "motion_type") or "Unknown"
        by_type[mt]["count"] += 1
        if _is_run(e):
            by_type[mt]["runs"] += 1
        elif _is_pass(e):
            by_type[mt]["passes"] += 1
        if e.yards_gained is not None:
            by_type[mt]["yards"].append(e.yards_gained)
        if e.play_type:
            by_type[mt]["concepts"].append(e.play_type)

    motion_type_summary = {}
    for mt, d in by_type.items():
        ys = d["yards"]
        motion_type_summary[mt] = {
            "count": d["count"],
            "run_pct": round(d["runs"] / d["count"] * 100, 1) if d["count"] else 0,
            "pass_pct": round(d["passes"] / d["count"] * 100, 1) if d["count"] else 0,
            "avg_yards": round(sum(ys) / len(ys), 1) if ys else 0,
            "top_concepts": dict(Counter(d["concepts"]).most_common(3)),
        }

    return {
        "motion_pct": motion_pct,
        "motion_success_rate": round(len(motion_success) / len(motion_plays) * 100, 1) if motion_plays else 0,
        "no_motion_success_rate": round(len(no_motion_success) / len(no_motion) * 100, 1) if no_motion else 0,
        "by_motion_type": motion_type_summary,
    }


def _flag_fourth_down(plays) -> Dict[str, Any]:
    """4th down plays: go-for-it analysis, top formations, routes, field position."""
    fourth = [e for e in plays if e.down == 4]
    if not fourth:
        return {"total": 0}
    success = [e for e in fourth if _is_success_flag(e)]
    top_formations = Counter(e.formation for e in fourth if e.formation)
    top_routes = Counter(e.play_type for e in fourth if e.play_type)
    own = [e for e in fourth if (e.field_position or "").upper().startswith("OWN")]
    opp = [e for e in fourth if (e.field_position or "").upper().startswith("OPP")]
    return {
        "total": len(fourth),
        "go_for_it_count": len(fourth),
        "success_rate": round(len(success) / len(fourth) * 100, 1) if fourth else 0,
        "top_formations": dict(top_formations.most_common(5)),
        "top_routes": dict(top_routes.most_common(5)),
        "own_territory": len(own),
        "opp_territory": len(opp),
    }


def _flag_blitz_response(plays) -> Dict[str, Any]:
    """How QB responds under defensive pressure."""
    pressure_plays = [e for e in plays if _x(e, "pressure_type") is not None]
    total = len(plays)
    if not pressure_plays:
        return {"pressure_rate": 0, "pressure_plays": 0}

    quick_release = []
    scrambles = []
    held_too_long = []

    for e in pressure_plays:
        result = (e.result or "").lower()
        if _is_run(e) or _x(e, "run_direction") is not None:
            scrambles.append(e)
        elif _is_pass(e) and result in ("gain", "first down", "touchdown"):
            quick_release.append(e)
        elif result in ("sack", "incomplete", "loss"):
            held_too_long.append(e)
        else:
            quick_release.append(e)

    success_under_pressure = [e for e in pressure_plays if _is_success_flag(e)]
    return {
        "pressure_rate": round(len(pressure_plays) / total * 100, 1) if total else 0,
        "pressure_plays": len(pressure_plays),
        "quick_release": len(quick_release),
        "scrambles": len(scrambles),
        "held_too_long": len(held_too_long),
        "success_under_pressure": round(len(success_under_pressure) / len(pressure_plays) * 100, 1) if pressure_plays else 0,
    }


def _flag_formation_route_matrix(plays) -> Dict[str, Any]:
    """Per formation: top 5 routes with count and success rate."""
    passes = [e for e in plays if _is_pass(e)]
    if not passes:
        return {}
    matrix = defaultdict(lambda: defaultdict(lambda: {"count": 0, "success": 0}))
    for e in passes:
        formation = e.formation or "Unknown"
        route = e.play_type or "Unknown"
        matrix[formation][route]["count"] += 1
        if _is_success_flag(e):
            matrix[formation][route]["success"] += 1

    result = {}
    for formation, routes in matrix.items():
        top_routes = sorted(routes.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
        result[formation] = {
            route: {
                "count": d["count"],
                "success_rate": round(d["success"] / d["count"] * 100, 1) if d["count"] else 0,
            }
            for route, d in top_routes
        }
    return result


def _flag_down_concept(plays) -> Dict[str, Any]:
    """By down: top routes, formations, success rate, scramble rate. 3rd down distance buckets."""
    result = {}
    for down in (1, 2, 3, 4):
        dp = [e for e in plays if e.down == down]
        if not dp:
            result[f"down_{down}"] = {"total": 0}
            continue
        runs = [e for e in dp if _is_run(e)]
        passes = [e for e in dp if _is_pass(e)]
        success = [e for e in dp if _is_success_flag(e)]
        result[f"down_{down}"] = {
            "total": len(dp),
            "top_routes": dict(Counter(e.play_type for e in passes if e.play_type).most_common(5)),
            "top_formations": dict(Counter(e.formation for e in dp if e.formation).most_common(5)),
            "success_rate": round(len(success) / len(dp) * 100, 1) if dp else 0,
            "scramble_rate": round(len(runs) / len(dp) * 100, 1) if dp else 0,
        }

    third = [e for e in plays if e.down == 3]
    third_short = [e for e in third if e.distance and e.distance < 3]
    third_medium = [e for e in third if e.distance and 3 <= e.distance <= 6]
    third_long = [e for e in third if e.distance and e.distance >= 7]

    def _bucket_summary(bucket):
        if not bucket:
            return {"total": 0}
        passes_b = [e for e in bucket if _is_pass(e)]
        success_b = [e for e in bucket if _is_success_flag(e)]
        return {
            "total": len(bucket),
            "top_routes": dict(Counter(e.play_type for e in passes_b if e.play_type).most_common(3)),
            "success_rate": round(len(success_b) / len(bucket) * 100, 1),
            "top_formations": dict(Counter(e.formation for e in bucket if e.formation).most_common(3)),
        }

    result["third_down_distance"] = {
        "short_under_3": _bucket_summary(third_short),
        "medium_3_to_6": _bucket_summary(third_medium),
        "long_7_plus": _bucket_summary(third_long),
    }
    return result


def _flag_game_script(plays) -> Dict[str, Any]:
    """By score situation: run/pass split, top routes, scramble rate, success rate."""
    situations = defaultdict(list)
    for e in plays:
        situation = _x(e, "score_situation") or "Unknown"
        situations[situation].append(e)

    result = {}
    for situation, sp in situations.items():
        runs = [e for e in sp if _is_run(e)]
        passes = [e for e in sp if _is_pass(e)]
        success = [e for e in sp if _is_success_flag(e)]
        rp = len(runs) + len(passes)
        result[situation] = {
            "total": len(sp),
            "run_pct": round(len(runs) / rp * 100, 1) if rp else 0,
            "pass_pct": round(len(passes) / rp * 100, 1) if rp else 0,
            "top_routes": dict(Counter(e.play_type for e in passes if e.play_type).most_common(5)),
            "scramble_rate": round(len(runs) / len(sp) * 100, 1) if sp else 0,
            "success_rate": round(len(success) / len(sp) * 100, 1) if sp else 0,
        }
    return result


def _flag_tempo_analysis(plays) -> Dict[str, Any]:
    """Tempo analysis: no-huddle/hurry-up rates, per-tempo success and scramble rate."""
    total = len(plays)
    if not total:
        return {}

    no_huddle = [e for e in plays if (_x(e, "tempo") or "").lower() in ("no-huddle", "no huddle")]
    hurry_up = [e for e in plays if (_x(e, "tempo") or "").lower() in ("hurry up", "hurry-up", "hurry")]

    tempos = defaultdict(list)
    for e in plays:
        tempo = _x(e, "tempo") or "Normal"
        tempos[tempo].append(e)

    per_tempo = {}
    for tempo, tp in tempos.items():
        runs = [e for e in tp if _is_run(e)]
        success = [e for e in tp if _is_success_flag(e)]
        per_tempo[tempo] = {
            "count": len(tp),
            "success_rate": round(len(success) / len(tp) * 100, 1) if tp else 0,
            "scramble_rate": round(len(runs) / len(tp) * 100, 1) if tp else 0,
        }

    return {
        "no_huddle_rate": round(len(no_huddle) / total * 100, 1),
        "hurry_up_rate": round(len(hurry_up) / total * 100, 1),
        "by_tempo": per_tempo,
    }


def _flag_short_yardage(plays) -> Dict[str, Any]:
    """3rd & 1-2 and 4th & 1-2 analysis."""
    short = [e for e in plays if e.down in (3, 4) and e.distance and e.distance <= 2]
    if not short:
        return {"total": 0}
    success = [e for e in short if _is_success_flag(e)]
    top_routes = Counter(e.play_type for e in short if e.play_type)
    top_formations = Counter(e.formation for e in short if e.formation)
    return {
        "total": len(short),
        "success_rate": round(len(success) / len(short) * 100, 1) if short else 0,
        "top_routes": dict(top_routes.most_common(5)),
        "top_formations": dict(top_formations.most_common(5)),
    }


def analyze_flag_football(events) -> Dict[str, Any]:
    """Full flag football deep analysis. Events are pre-filtered to offense only."""
    plays = [e for e in events if e.event_type in ("run", "pass", "play", "penalty") or bool(e.play_type)]
    total = len(plays)
    if total == 0:
        return {"total_plays": 0}

    runs = [e for e in plays if _is_run(e)]
    passes = [e for e in plays if _is_pass(e)]
    rp_total = len(runs) + len(passes)

    yards = [e.yards_gained for e in plays if e.yards_gained is not None]
    avg_yards = round(sum(yards) / len(yards), 1) if yards else 0

    results = Counter(e.result for e in plays if e.result)
    formations = Counter(e.formation for e in plays if e.formation)

    by_down = defaultdict(list)
    for e in plays:
        if e.down:
            by_down[e.down].append(e)

    return {
        "total_plays": total,
        "run_plays": len(runs),
        "pass_plays": len(passes),
        "run_pass_ratio": {
            "run_pct": round(len(runs) / rp_total * 100, 1) if rp_total else 0,
            "pass_pct": round(len(passes) / rp_total * 100, 1) if rp_total else 0,
        },
        "top_formations": dict(formations.most_common(8)),
        "play_results": dict(results.most_common(10)),
        "avg_yards": avg_yards,
        "down_tendencies": {
            f"down_{d}": _down_summary(ps) for d, ps in by_down.items()
        },
        "route_analysis": _route_analysis(passes),
        "receiver_zone_targeting": _receiver_zone_targeting(passes),
        "scramble_analysis": _scramble_analysis(plays),
        "end_zone": _flag_end_zone(plays),
        "motion_analysis": _flag_motion_analysis(plays),
        "fourth_down": _flag_fourth_down(plays),
        "blitz_response": _flag_blitz_response(plays),
        "formation_route_matrix": _flag_formation_route_matrix(plays),
        "down_concept": _flag_down_concept(plays),
        "game_script": _flag_game_script(plays),
        "tempo_analysis": _flag_tempo_analysis(plays),
        "short_yardage": _flag_short_yardage(plays),
    }
