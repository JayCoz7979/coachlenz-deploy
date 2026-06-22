from typing import List, Dict, Any
from collections import Counter, defaultdict


def _x(e, key, default=None):
    ed = getattr(e, "extra_data", None)
    if not ed:
        return default
    return ed.get(key, default)


def _is_made(e) -> bool:
    return (e.result or "").lower() in ("made", "good", "and-1")


def _is_three(e) -> bool:
    zone = _x(e, "shot_zone") or ""
    return "3" in zone or "Corner" in zone or "Wing 3" in zone or "Top of Key" in zone


def _is_paint(e) -> bool:
    zone = _x(e, "shot_zone") or ""
    return zone in ("Restricted Area", "Paint Non-RA")


def _is_mid_range(e) -> bool:
    zone = _x(e, "shot_zone") or ""
    return "Mid" in zone or "Elbow" in zone


def analyze_basketball(events) -> Dict[str, Any]:
    if not events:
        return {"total_plays": 0}

    shots = [e for e in events if e.event_type == "shot"]
    turnovers = [e for e in events if e.event_type == "turnover"]
    fouls = [e for e in events if e.event_type == "foul"]
    rebounds = [e for e in events if e.event_type == "rebound"]
    steals = [e for e in events if e.event_type == "steal"]
    blocks = [e for e in events if e.event_type == "block"]
    timeouts = [e for e in events if e.event_type == "timeout"]

    offense_events = [e for e in events if (e.side or "offense") in ("offense", "transition")]
    defense_events = [e for e in events if (e.side or "offense") == "defense"]

    return {
        "total_plays": len(events),
        "offense_plays": len(offense_events),
        "defense_plays": len(defense_events),
        "shooting_overview": _shooting_overview(shots),
        "shot_zone_map": _shot_zone_map(shots),
        "shot_creation": _shot_creation(shots),
        "pick_and_roll": _pick_and_roll_analysis(offense_events),
        "isolation": _isolation_analysis(offense_events),
        "post_up": _post_up_analysis(offense_events),
        "transition": _transition_analysis(events),
        "paint_and_drive": _paint_drive_analysis(offense_events),
        "screen_usage": _screen_analysis(offense_events),
        "inbound_plays": _inbound_analysis(offense_events),
        "shot_clock": _shot_clock_analysis(shots),
        "quarter_breakdown": _quarter_breakdown(events),
        "game_script": _game_script_analysis(events),
        "defensive_scheme": _defensive_scheme_analysis(defense_events),
        "ball_screen_defense": _ball_screen_defense_analysis(defense_events),
        "turnovers": _turnover_analysis(turnovers),
        "fouls": _foul_analysis(fouls),
        "rebounding": _rebound_analysis(rebounds),
        "steals": len(steals),
        "blocks": len(blocks),
        "timeouts_used": len(timeouts),
    }


def _shooting_overview(shots) -> Dict[str, Any]:
    if not shots:
        return {"total_shots": 0}

    makes = [e for e in shots if _is_made(e)]
    threes = [e for e in shots if _is_three(e)]
    threes_made = [e for e in threes if _is_made(e)]
    paint = [e for e in shots if _is_paint(e)]
    paint_made = [e for e in paint if _is_made(e)]
    mid = [e for e in shots if _is_mid_range(e)]
    mid_made = [e for e in mid if _is_made(e)]

    return {
        "total_shots": len(shots),
        "total_made": len(makes),
        "overall_fg_pct": round(len(makes) / len(shots) * 100, 1),
        "three_point": {
            "attempts": len(threes),
            "made": len(threes_made),
            "fg_pct": round(len(threes_made) / len(threes) * 100, 1) if threes else 0,
            "pct_of_shots": round(len(threes) / len(shots) * 100, 1),
        },
        "paint": {
            "attempts": len(paint),
            "made": len(paint_made),
            "fg_pct": round(len(paint_made) / len(paint) * 100, 1) if paint else 0,
            "pct_of_shots": round(len(paint) / len(shots) * 100, 1),
        },
        "mid_range": {
            "attempts": len(mid),
            "made": len(mid_made),
            "fg_pct": round(len(mid_made) / len(mid) * 100, 1) if mid else 0,
            "pct_of_shots": round(len(mid) / len(shots) * 100, 1),
        },
    }


def _shot_zone_map(shots) -> Dict[str, Any]:
    if not shots:
        return {}

    by_zone = defaultdict(list)
    for e in shots:
        zone = _x(e, "shot_zone")
        if zone:
            by_zone[zone].append(e)

    zone_map = {}
    for zone, zshots in sorted(by_zone.items(), key=lambda x: -len(x[1])):
        makes = [e for e in zshots if _is_made(e)]
        zone_map[zone] = {
            "attempts": len(zshots),
            "made": len(makes),
            "fg_pct": round(len(makes) / len(zshots) * 100, 1),
            "pct_of_all_shots": round(len(zshots) / len(shots) * 100, 1),
        }

    if not zone_map:
        return {}

    return {
        "zones": zone_map,
        "hottest_zone": max(zone_map, key=lambda z: zone_map[z]["fg_pct"]),
        "most_frequent_zone": max(zone_map, key=lambda z: zone_map[z]["attempts"]),
        "left_side_pct": round(sum(v["attempts"] for k, v in zone_map.items() if "Left" in k) / len(shots) * 100, 1),
        "right_side_pct": round(sum(v["attempts"] for k, v in zone_map.items() if "Right" in k) / len(shots) * 100, 1),
        "corner_three_pct": round(
            sum(v["attempts"] for k, v in zone_map.items() if "Corner" in k) / len(shots) * 100, 1
        ),
    }


def _shot_creation(shots) -> Dict[str, Any]:
    if not shots:
        return {"total": 0}

    by_type = defaultdict(list)
    for e in shots:
        st = _x(e, "shot_type")
        if st:
            by_type[st].append(e)

    type_detail = {}
    for st, sp in sorted(by_type.items(), key=lambda x: -len(x[1])):
        makes = [e for e in sp if _is_made(e)]
        type_detail[st] = {
            "attempts": len(sp),
            "made": len(makes),
            "fg_pct": round(len(makes) / len(sp) * 100, 1),
            "pct_of_shots": round(len(sp) / len(shots) * 100, 1),
        }

    by_action = defaultdict(list)
    for e in shots:
        pa = _x(e, "play_action")
        if pa:
            by_action[pa].append(e)

    action_detail = {}
    for pa, ap in sorted(by_action.items(), key=lambda x: -len(x[1])):
        makes = [e for e in ap if _is_made(e)]
        action_detail[pa] = {
            "attempts": len(ap),
            "made": len(makes),
            "fg_pct": round(len(makes) / len(ap) * 100, 1),
            "pct_of_shots": round(len(ap) / len(shots) * 100, 1),
        }

    return {
        "total_shots": len(shots),
        "by_shot_type": type_detail,
        "by_play_action": action_detail,
        "best_action": max(action_detail, key=lambda k: action_detail[k]["fg_pct"]) if action_detail else None,
        "most_used_action": max(action_detail, key=lambda k: action_detail[k]["attempts"]) if action_detail else None,
    }


def _pick_and_roll_analysis(events) -> Dict[str, Any]:
    pnr = [e for e in events if _x(e, "play_action") in ("Pick and Roll", "Pick and Pop")]
    if not pnr:
        return {"total": 0}

    rolls = [e for e in pnr if _x(e, "play_action") == "Pick and Roll"]
    pops = [e for e in pnr if _x(e, "play_action") == "Pick and Pop"]
    shots_pnr = [e for e in pnr if e.event_type == "shot"]
    made_pnr = [e for e in shots_pnr if _is_made(e)]
    tos_pnr = [e for e in pnr if e.event_type == "turnover"]

    by_position = defaultdict(list)
    for e in pnr:
        pos = _x(e, "ball_screen_position")
        if pos:
            by_position[pos].append(e)

    pos_detail = {}
    for pos, pp in sorted(by_position.items(), key=lambda x: -len(x[1])):
        pshots = [e for e in pp if e.event_type == "shot"]
        pmakes = [e for e in pshots if _is_made(e)]
        pos_detail[pos] = {
            "count": len(pp),
            "shot_attempts": len(pshots),
            "fg_pct": round(len(pmakes) / len(pshots) * 100, 1) if pshots else 0,
        }

    return {
        "total_pnr": len(pnr),
        "pct_of_offense": round(len(pnr) / max(len(events), 1) * 100, 1),
        "roll_count": len(rolls),
        "pop_count": len(pops),
        "roll_pct": round(len(rolls) / len(pnr) * 100, 1),
        "shot_attempts": len(shots_pnr),
        "fg_pct": round(len(made_pnr) / len(shots_pnr) * 100, 1) if shots_pnr else 0,
        "turnovers": len(tos_pnr),
        "by_screen_position": pos_detail,
        "preferred_position": max(pos_detail, key=lambda k: pos_detail[k]["count"]) if pos_detail else None,
    }


def _isolation_analysis(events) -> Dict[str, Any]:
    iso = [e for e in events if _x(e, "play_action") == "Isolation"]
    if not iso:
        return {"total": 0}

    shots = [e for e in iso if e.event_type == "shot"]
    makes = [e for e in shots if _is_made(e)]
    tos = [e for e in iso if e.event_type == "turnover"]

    by_zone = defaultdict(list)
    for e in shots:
        zone = _x(e, "shot_zone")
        if zone:
            by_zone[zone].append(e)

    zone_detail = {}
    for zone, zp in sorted(by_zone.items(), key=lambda x: -len(x[1])):
        zm = [e for e in zp if _is_made(e)]
        zone_detail[zone] = {
            "attempts": len(zp),
            "fg_pct": round(len(zm) / len(zp) * 100, 1),
        }

    return {
        "total_iso": len(iso),
        "pct_of_offense": round(len(iso) / max(len(events), 1) * 100, 1),
        "shot_attempts": len(shots),
        "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
        "turnovers": len(tos),
        "by_zone": zone_detail,
    }


def _post_up_analysis(events) -> Dict[str, Any]:
    post = [e for e in events if _x(e, "play_action") == "Post Up"]
    if not post:
        return {"total": 0}

    shots = [e for e in post if e.event_type == "shot"]
    makes = [e for e in shots if _is_made(e)]
    tos = [e for e in post if e.event_type == "turnover"]
    kick_outs = [e for e in post if _x(e, "kick_out")]

    return {
        "total_post": len(post),
        "pct_of_offense": round(len(post) / max(len(events), 1) * 100, 1),
        "shot_attempts": len(shots),
        "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
        "turnovers": len(tos),
        "kick_out_count": len(kick_outs),
    }


def _transition_analysis(events) -> Dict[str, Any]:
    transition = [e for e in events if e.side == "transition" or _x(e, "transition_type")]
    if not transition:
        return {"total": 0}

    shots = [e for e in transition if e.event_type == "shot"]
    makes = [e for e in shots if _is_made(e)]
    by_type = Counter(_x(e, "transition_type") for e in transition if _x(e, "transition_type"))

    return {
        "total": len(transition),
        "by_type": dict(by_type.most_common(4)),
        "shot_attempts": len(shots),
        "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
        "primary_break_count": by_type.get("Primary Break", 0),
        "pct_of_offense": round(len(transition) / max(len(events), 1) * 100, 1),
    }


def _paint_drive_analysis(events) -> Dict[str, Any]:
    paint_touches = [e for e in events if _x(e, "paint_touch")]
    kick_outs = [e for e in events if _x(e, "kick_out")]
    paint_shots = [e for e in events if e.event_type == "shot" and _is_paint(e)]
    paint_made = [e for e in paint_shots if _is_made(e)]
    drive_kick = [e for e in events if _x(e, "play_action") == "Drive and Kick"]

    return {
        "paint_touch_count": len(paint_touches),
        "kick_out_count": len(kick_outs),
        "paint_shot_attempts": len(paint_shots),
        "paint_fg_pct": round(len(paint_made) / len(paint_shots) * 100, 1) if paint_shots else 0,
        "drive_and_kick_count": len(drive_kick),
    }


def _screen_analysis(events) -> Dict[str, Any]:
    screened = [e for e in events if _x(e, "screen_type")]
    if not screened:
        return {"total": 0}

    by_type = defaultdict(list)
    for e in screened:
        st = _x(e, "screen_type")
        by_type[st].append(e)

    type_detail = {}
    for st, sp in sorted(by_type.items(), key=lambda x: -len(x[1])):
        shots = [e for e in sp if e.event_type == "shot"]
        makes = [e for e in shots if _is_made(e)]
        type_detail[st] = {
            "count": len(sp),
            "shot_attempts": len(shots),
            "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
        }

    return {
        "total": len(screened),
        "by_type": type_detail,
        "most_used": max(type_detail, key=lambda k: type_detail[k]["count"]) if type_detail else None,
    }


def _inbound_analysis(events) -> Dict[str, Any]:
    blobs = [e for e in events if _x(e, "play_action") == "BLOB"]
    slobs = [e for e in events if _x(e, "play_action") == "SLOB"]
    if not blobs and not slobs:
        return {"total": 0}

    blob_shots = [e for e in blobs if e.event_type == "shot"]
    blob_makes = [e for e in blob_shots if _is_made(e)]
    slob_shots = [e for e in slobs if e.event_type == "shot"]
    slob_makes = [e for e in slob_shots if _is_made(e)]

    return {
        "total": len(blobs) + len(slobs),
        "blob": {
            "count": len(blobs),
            "shot_attempts": len(blob_shots),
            "fg_pct": round(len(blob_makes) / len(blob_shots) * 100, 1) if blob_shots else 0,
        },
        "slob": {
            "count": len(slobs),
            "shot_attempts": len(slob_shots),
            "fg_pct": round(len(slob_makes) / len(slob_shots) * 100, 1) if slob_shots else 0,
        },
    }


def _shot_clock_analysis(shots) -> Dict[str, Any]:
    if not shots:
        return {"total": 0}

    by_range = defaultdict(list)
    for e in shots:
        scr = _x(e, "shot_clock_range")
        if scr:
            by_range[scr].append(e)

    range_detail = {}
    for scr, sp in sorted(by_range.items(), key=lambda x: -len(x[1])):
        makes = [e for e in sp if _is_made(e)]
        range_detail[scr] = {
            "attempts": len(sp),
            "fg_pct": round(len(makes) / len(sp) * 100, 1),
            "pct_of_shots": round(len(sp) / len(shots) * 100, 1),
        }

    late = by_range.get("Late (<7s)", [])
    late_makes = [e for e in late if _is_made(e)]

    return {
        "total_shots": len(shots),
        "by_range": range_detail,
        "late_clock_pct": round(len(late) / len(shots) * 100, 1) if shots else 0,
        "late_clock_fg_pct": round(len(late_makes) / len(late) * 100, 1) if late else 0,
    }


def _quarter_breakdown(events) -> Dict[str, Any]:
    by_quarter = defaultdict(list)
    for e in events:
        q = _x(e, "quarter")
        if q:
            by_quarter[q].append(e)

    detail = {}
    for q in sorted(by_quarter.keys()):
        qe = by_quarter[q]
        shots = [e for e in qe if e.event_type == "shot"]
        makes = [e for e in shots if _is_made(e)]
        threes = [e for e in shots if _is_three(e)]
        paint = [e for e in shots if _is_paint(e)]
        tos = [e for e in qe if e.event_type == "turnover"]
        detail[f"Q{q}"] = {
            "events": len(qe),
            "shot_attempts": len(shots),
            "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
            "three_attempts": len(threes),
            "paint_attempts": len(paint),
            "turnovers": len(tos),
        }

    return detail


def _game_script_analysis(events) -> Dict[str, Any]:
    by_margin = defaultdict(list)
    for e in events:
        margin = _x(e, "score_margin")
        if margin:
            by_margin[margin].append(e)

    if not by_margin:
        return {"total": 0}

    detail = {}
    for margin, me in sorted(by_margin.items(), key=lambda x: -len(x[1])):
        shots = [e for e in me if e.event_type == "shot"]
        makes = [e for e in shots if _is_made(e)]
        threes = [e for e in shots if _is_three(e)]
        tos = [e for e in me if e.event_type == "turnover"]
        detail[margin] = {
            "count": len(me),
            "shot_attempts": len(shots),
            "fg_pct": round(len(makes) / len(shots) * 100, 1) if shots else 0,
            "three_pt_rate": round(len(threes) / len(shots) * 100, 1) if shots else 0,
            "turnovers": len(tos),
        }

    return detail


def _defensive_scheme_analysis(events) -> Dict[str, Any]:
    if not events:
        return {"total": 0}

    schemes = Counter(_x(e, "defensive_scheme") for e in events if _x(e, "defensive_scheme"))
    total = sum(schemes.values())
    if not total:
        return {"total": 0}

    scheme_detail = {}
    for scheme, count in schemes.most_common(6):
        se = [e for e in events if _x(e, "defensive_scheme") == scheme]
        by_q = Counter(_x(e, "quarter") for e in se if _x(e, "quarter"))
        scheme_detail[scheme] = {
            "count": count,
            "pct": round(count / total * 100, 1),
            "quarters_used": dict(by_q.most_common(4)),
        }

    man_pct = round(schemes.get("Man", 0) / total * 100, 1)
    zone_count = sum(v for k, v in schemes.items() if "Zone" in k)
    press_count = sum(v for k, v in schemes.items() if "Press" in k or "Trap" in k)

    return {
        "total": total,
        "primary_scheme": schemes.most_common(1)[0][0],
        "man_pct": man_pct,
        "zone_pct": round(zone_count / total * 100, 1),
        "press_count": press_count,
        "by_scheme": scheme_detail,
    }


def _ball_screen_defense_analysis(events) -> Dict[str, Any]:
    hedge_plays = [e for e in events if _x(e, "hedge_style")]
    if not hedge_plays:
        return {"total": 0}

    by_hedge = Counter(_x(e, "hedge_style") for e in hedge_plays)
    help_styles = Counter(_x(e, "help_defense") for e in events if _x(e, "help_defense"))
    deny_styles = Counter(_x(e, "deny_style") for e in events if _x(e, "deny_style"))
    press_triggers = Counter(_x(e, "press_trigger") for e in events if _x(e, "press_trigger"))

    return {
        "total": len(hedge_plays),
        "primary_hedge": by_hedge.most_common(1)[0][0] if by_hedge else None,
        "hedge_distribution": dict(by_hedge.most_common(6)),
        "help_defense": dict(help_styles.most_common(4)),
        "deny_style": dict(deny_styles.most_common(3)),
        "press_triggers": dict(press_triggers.most_common(3)),
    }


def _turnover_analysis(turnovers) -> Dict[str, Any]:
    if not turnovers:
        return {"total": 0}

    by_type = Counter(
        _x(e, "play_action") or e.play_type
        for e in turnovers
        if (_x(e, "play_action") or e.play_type)
    )
    by_quarter = Counter(_x(e, "quarter") for e in turnovers if _x(e, "quarter"))

    return {
        "total": len(turnovers),
        "by_type": dict(by_type.most_common(8)),
        "by_quarter": {f"Q{k}": v for k, v in by_quarter.items()},
    }


def _foul_analysis(fouls) -> Dict[str, Any]:
    if not fouls:
        return {"total": 0}

    offensive = [e for e in fouls if (e.side or "") in ("offense", "transition")]
    defensive = [e for e in fouls if (e.side or "") == "defense"]

    return {
        "total": len(fouls),
        "offensive_fouls": len(offensive),
        "defensive_fouls": len(defensive),
    }


def _rebound_analysis(rebounds) -> Dict[str, Any]:
    if not rebounds:
        return {"total": 0}

    offensive = [e for e in rebounds if (e.side or "") in ("offense", "transition")]
    defensive = [e for e in rebounds if (e.side or "") == "defense"]

    return {
        "total": len(rebounds),
        "offensive": len(offensive),
        "defensive": len(defensive),
        "offensive_pct": round(len(offensive) / len(rebounds) * 100, 1) if rebounds else 0,
    }
