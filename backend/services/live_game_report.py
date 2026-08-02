"""
Bespoke Live Game report writer: the 9-section halftime / full-game report.

The live logger captures exactly the fields these nine sections need (quarter/half,
possession, opponent jersey numbers, special-teams units, running score, coaching
points): data the opponent-scout tendency engine never surfaces. So this writer
computes every stat DETERMINISTICALLY in Python (no invented numbers), then makes ONE
LLM call to write the coordinator-voice prose grounded in those numbers. That split
is deliberate: the counts are trustworthy because code counted them; the LLM only
turns them into "what a coordinator says to the head coach at halftime."

Reused from report_writer: the async client, model, robust section parser. The output
shape is identical ([{heading, insight_type, body}]) so /reports/[id] renders it with
no viewer changes.

Section maps (spec):
  Football / Flag Football:  1 Off Summary · 2 Off Players · 3 Def Summary ·
    4 Opp Players · 5 Special Teams · 6 Top 3 Adjustments · 7 Coaching Points ·
    8 Score & Momentum · 9 Season Trend (3+ games)
  Basketball: same nine, shot-zone / possession framed, with a Foul-Trouble alert.
"""
import json
from typing import List, Dict, Any, Optional

from backend.services.report_writer import client, MODEL, _first_text, _parse_report_sections

META_EVENT_TYPE = "game_meta"

SYSTEM_PROMPT_LIVE = """You are a veteran coordinator (20+ years, high school & college) briefing your head coach and players at HALFTIME or right after a game. You are NOT reading a box score: you are telling the staff what is actually happening and what to change.

RULES:
- Every number you cite comes from the provided computed stats. Never invent a stat. The counts were computed by code: trust them, do not recompute or second-guess them.
- Talk like a coordinator in the locker room: direct, specific, urgent, plain language. "We're living on 2nd-and-long because we keep running A-gap into a loaded box": not "the offense exhibited suboptimal efficiency."
- Always pair a percentage with its count: "3rd down: 2 of 9 (22%)".
- Lead each section with the single most important thing, then bullets for the specifics.
- The Top 3 Adjustments section is the point of the whole report: three concrete, callable changes, each tied to a specific stat above, each written the way you'd say it to the position group.
- If a section's data is thin or empty, say so in one line and move on: do not pad.
- Bold the key numbers and calls with **double asterisks** so they pop when scanned.
- Never use em dashes. Use commas, colons, or periods instead.
"""


# ── small deterministic helpers ──────────────────────────────────────────────
def _int(x, default=0) -> int:
    try:
        if x is None or x == "":
            return default
        return int(float(x))
    except (TypeError, ValueError):
        return default


def _extra(e) -> Dict[str, Any]:
    return getattr(e, "extra_data", None) or {}


def _rp(v) -> str:
    return str(v or "").strip().lower()


def _is_run(pt: str) -> bool:
    p = _rp(pt)
    return any(k in p for k in ("run", "sneak", "scramble", "kneel"))


def _is_pass(pt: str) -> bool:
    p = _rp(pt)
    return "pass" in p or "rpo" in p


def _in_red_zone(field_position: Optional[str]) -> bool:
    """OPP 1-20 = inside the opponent's 20."""
    fp = _rp(field_position)
    if fp.startswith("opp"):
        n = _int("".join(ch for ch in fp if ch.isdigit()), 99)
        return 0 < n <= 20
    return False


def _converted(e) -> bool:
    """Did this offensive play move the chains / score?"""
    res = _rp(getattr(e, "result", "")) + " " + _rp(_extra(e).get("pass_result"))
    if any(k in res for k in ("first down", "touchdown", "td")):
        return True
    yg = getattr(e, "yards_gained", None)
    dist = getattr(e, "distance", None)
    return yg is not None and dist is not None and yg >= dist


def _pct(n: int, d: int) -> Optional[float]:
    return round(100 * n / d, 1) if d else None


def _rank(counter: Dict[str, int], top: int = 6) -> List[Dict[str, Any]]:
    return [{"key": k, "count": v} for k, v in
            sorted(counter.items(), key=lambda kv: -kv[1])[:top]]


def _split_plays(events):
    """Return (plays, meta, coaching_points) from a mixed live-game event list."""
    plays = [e for e in events if getattr(e, "event_type", None) == "play"]
    meta = next((e for e in events if getattr(e, "event_type", None) == META_EVENT_TYPE), None)
    return plays, meta


# ── football / flag football stats ───────────────────────────────────────────
def compute_football_stats(events, config: Dict[str, Any]) -> Dict[str, Any]:
    plays, _ = _split_plays(events)
    off = [e for e in plays if (e.side or "offense") == "offense"]
    deff = [e for e in plays if e.side == "defense"]
    st = [e for e in plays if e.side == "special_teams"]

    # ── Section 1: our offense ──
    off_yards = sum(_int(getattr(e, "yards_gained", 0)) for e in off)
    runs = [e for e in off if _is_run(e.play_type)]
    passes = [e for e in off if _is_pass(e.play_type)]
    run_yards = sum(_int(getattr(e, "yards_gained", 0)) for e in runs)
    pass_yards = sum(_int(getattr(e, "yards_gained", 0)) for e in passes)
    third = [e for e in off if _int(getattr(e, "down", 0)) == 3]
    third_conv = [e for e in third if _converted(e)]
    rz = [e for e in off if _in_red_zone(getattr(e, "field_position", None))]
    rz_scores = [e for e in rz if "touchdown" in _rp(e.result) or "td" in _rp(e.result)]
    form_yards: Dict[str, list] = {}
    for e in off:
        if e.formation:
            form_yards.setdefault(e.formation, []).append(_int(getattr(e, "yards_gained", 0)))

    def _by_down_situation(pred):
        sel = [e for e in off if pred(e)]
        rc, pc = sum(1 for e in sel if _is_run(e.play_type)), sum(1 for e in sel if _is_pass(e.play_type))
        return {"plays": len(sel), "run": rc, "pass": pc}

    offense = {
        "plays": len(off), "total_yards": off_yards,
        "yards_per_play": round(off_yards / len(off), 2) if off else 0,
        "run": {"plays": len(runs), "yards": run_yards, "ypc": round(run_yards / len(runs), 2) if runs else 0},
        "pass": {"plays": len(passes), "yards": pass_yards,
                 "completions": sum(1 for e in passes if "completion" in _rp(_extra(e).get("pass_result"))),
                 "ypa": round(pass_yards / len(passes), 2) if passes else 0},
        "run_pass_ratio": f"{len(runs)}:{len(passes)}",
        "third_down": {"attempts": len(third), "conversions": len(third_conv), "pct": _pct(len(third_conv), len(third))},
        "red_zone": {"trips_plays": len(rz), "touchdowns": len(rz_scores)},
        "formations": sorted(
            ({"formation": f, "plays": len(v), "yards": sum(v),
              "ypp": round(sum(v) / len(v), 2) if v else 0} for f, v in form_yards.items()),
            key=lambda d: -d["yards"]),
        "second_and_long": _by_down_situation(lambda e: _int(e.down) == 2 and _int(e.distance) >= 8),
        "third_and_short": _by_down_situation(lambda e: _int(e.down) == 3 and _int(e.distance) <= 3),
        "scoring_plays": [_play_tag(e) for e in off if "touchdown" in _rp(e.result) or "td" in _rp(e.result)],
    }

    # ── Section 2: our offensive players ──
    carriers, targets, passers = {}, {}, {}
    for e in runs:
        j = _extra(e).get("ball_carrier_jersey") or e.player
        if j:
            d = carriers.setdefault(str(j), {"carries": 0, "yards": 0, "gaps": {}})
            d["carries"] += 1
            d["yards"] += _int(getattr(e, "yards_gained", 0))
            g = _extra(e).get("run_gap") or _extra(e).get("rush_lane")
            if g:
                d["gaps"][g] = d["gaps"].get(g, 0) + 1
    for e in passes:
        t = _extra(e).get("target_jersey")
        if t:
            d = targets.setdefault(str(t), {"targets": 0, "catches": 0, "yards": 0, "routes": {}})
            d["targets"] += 1
            if "completion" in _rp(_extra(e).get("pass_result")):
                d["catches"] += 1
                d["yards"] += _int(getattr(e, "yards_gained", 0))
            r = _extra(e).get("route")
            if r:
                d["routes"][r] = d["routes"].get(r, 0) + 1
        p = _extra(e).get("passer_jersey")
        if p:
            d = passers.setdefault(str(p), {"attempts": 0, "completions": 0, "yards": 0})
            d["attempts"] += 1
            if "completion" in _rp(_extra(e).get("pass_result")):
                d["completions"] += 1
                d["yards"] += _int(getattr(e, "yards_gained", 0))

    used = {str(j) for j in (
        [c for c in carriers] + [t for t in targets] + [p for p in passers])}
    roster = config.get("our_roster") or []
    unused = [r for r in roster if str(r.get("jersey")) not in used]

    players_off = {
        "ball_carriers": [{"jersey": k, **v, "ypc": round(v["yards"] / v["carries"], 2) if v["carries"] else 0}
                          for k, v in sorted(carriers.items(), key=lambda kv: -kv[1]["yards"])],
        "targets": [{"jersey": k, **v} for k, v in sorted(targets.items(), key=lambda kv: -kv[1]["targets"])],
        "passers": [{"jersey": k, **v} for k, v in sorted(passers.items(), key=lambda kv: -kv[1]["attempts"])],
        "unused_roster": unused,
    }

    # ── Section 3: our defense ──
    def_yards = sum(_int(getattr(e, "yards_gained", 0)) for e in deff)
    opp_forms, opp_types, opp_gaps = {}, {}, {}
    front_perf: Dict[str, list] = {}
    for e in deff:
        x = _extra(e)
        if x.get("opp_formation"):
            opp_forms[x["opp_formation"]] = opp_forms.get(x["opp_formation"], 0) + 1
        if x.get("opp_play_type"):
            opp_types[x["opp_play_type"]] = opp_types.get(x["opp_play_type"], 0) + 1
        if x.get("opp_run_gap"):
            opp_gaps[x["opp_run_gap"]] = opp_gaps.get(x["opp_run_gap"], 0) + 1
        if e.defensive_front:
            front_perf.setdefault(e.defensive_front, []).append(_int(getattr(e, "yards_gained", 0)))
    def_third = [e for e in deff if _int(getattr(e, "down", 0)) == 3]
    def_third_allowed = [e for e in def_third if _converted(e)]
    blitzes = [e for e in deff if _rp(e.blitz) in ("yes", "y", "true")]

    defense = {
        "plays": len(deff), "yards_allowed": def_yards,
        "yards_per_play_allowed": round(def_yards / len(deff), 2) if deff else 0,
        "opp_formations": _rank(opp_forms), "opp_play_types": _rank(opp_types), "opp_run_gaps": _rank(opp_gaps),
        "fronts": sorted(
            ({"front": f, "plays": len(v), "yards_allowed": sum(v),
              "ypp_allowed": round(sum(v) / len(v), 2) if v else 0} for f, v in front_perf.items()),
            key=lambda d: d["ypp_allowed"]),
        "third_down_allowed": {"attempts": len(def_third), "conversions_allowed": len(def_third_allowed),
                               "pct": _pct(len(def_third_allowed), len(def_third))},
        "pressure": {"blitzes": len(blitzes),
                     "avg_yards_when_blitzing": round(sum(_int(getattr(e, "yards_gained", 0)) for e in blitzes) / len(blitzes), 2) if blitzes else None},
        "coverages": _rank({e.coverage: 1 for e in deff if e.coverage} if False else _count_attr(deff, "coverage")),
    }

    # ── Section 4: opponent players (from the fields we logged on defense) ──
    opp_carriers, opp_targets, opp_routes = {}, {}, {}
    for e in deff:
        x = _extra(e)
        if x.get("opp_ball_carrier"):
            opp_carriers[str(x["opp_ball_carrier"])] = opp_carriers.get(str(x["opp_ball_carrier"]), 0) + 1
        if x.get("opp_target"):
            j = str(x["opp_target"])
            d = opp_targets.setdefault(j, {"targets": 0, "vs_coverage": {}})
            d["targets"] += 1
            if e.coverage:
                d["vs_coverage"][e.coverage] = d["vs_coverage"].get(e.coverage, 0) + 1
        if x.get("opp_route"):
            opp_routes[x["opp_route"]] = opp_routes.get(x["opp_route"], 0) + 1
    players_opp = {
        "ball_carriers": _rank(opp_carriers),
        "targets": [{"jersey": k, **v} for k, v in sorted(opp_targets.items(), key=lambda kv: -kv[1]["targets"])],
        "routes": _rank(opp_routes),
    }

    # ── Section 5: special teams ──
    st_by_unit: Dict[str, Dict[str, Any]] = {}
    for e in st:
        x = _extra(e)
        unit = x.get("st_unit") or "Special Teams"
        d = st_by_unit.setdefault(unit, {"count": 0, "results": {}, "yards": []})
        d["count"] += 1
        r = x.get("st_result") or e.result
        if r:
            d["results"][r] = d["results"].get(r, 0) + 1
        y = x.get("st_yards")
        if y not in (None, ""):
            d["yards"].append(_int(y))
    special = {"plays": len(st), "by_unit": [
        {"unit": u, "count": d["count"], "results": d["results"],
         "avg_yards": round(sum(d["yards"]) / len(d["yards"]), 1) if d["yards"] else None}
        for u, d in st_by_unit.items()]}

    return {"offense": offense, "players_offense": players_off,
            "defense": defense, "players_opponent": players_opp,
            "special_teams": special, "momentum": _score_momentum(plays, "quarter")}


def _count_attr(events, attr) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in events:
        v = getattr(e, attr, None)
        if v:
            out[v] = out.get(v, 0) + 1
    return out


def _play_tag(e) -> str:
    x = _extra(e)
    parts = []
    if getattr(e, "down", None):
        parts.append(f"{e.down}&{getattr(e, 'distance', '')}")
    parts.append(e.play_type or x.get("st_unit") or "play")
    if getattr(e, "yards_gained", None) is not None:
        parts.append(f"{_int(e.yards_gained):+d} yd")
    if e.result:
        parts.append(e.result)
    return " · ".join(str(p) for p in parts if p)


# ── basketball stats ─────────────────────────────────────────────────────────
_POSS_POINTS = {"2 pts": 2, "3 pts": 3, "1 pt ft": 1, "2 pt ft": 2}


def _poss_points(result: Optional[str]) -> int:
    return _POSS_POINTS.get(_rp(result), 0)


def _made(shot_result: Optional[str]) -> bool:
    return _rp(shot_result) in ("made", "and-1")


def compute_basketball_stats(events, config: Dict[str, Any]) -> Dict[str, Any]:
    plays, _ = _split_plays(events)
    off = [e for e in plays if (e.side or "offense") == "offense"]
    deff = [e for e in plays if e.side == "defense"]

    # ── Section 1: our offense ──
    points = sum(_poss_points(_extra(e).get("possession_result")) for e in off)
    zones, made_by_zone = {}, {}
    for e in off:
        z = _extra(e).get("shot_zone")
        if z:
            zones[z] = zones.get(z, 0) + 1
            if _made(_extra(e).get("shot_result")):
                made_by_zone[z] = made_by_zone.get(z, 0) + 1
    turnovers = [e for e in off if "turnover" in _rp(_extra(e).get("shot_result")) or "turnover" in _rp(_extra(e).get("possession_result"))]
    to_types = {}
    for e in turnovers:
        t = _extra(e).get("turnover_type")
        if t:
            to_types[t] = to_types.get(t, 0) + 1
    transition = [e for e in off if _rp(_extra(e).get("ball_entry")) == "transition"]
    specials = _special_situations(plays)

    offense = {
        "possessions": len(off), "points": points,
        "points_per_possession": round(points / len(off), 2) if off else 0,
        "shot_zones": [{"zone": z, "attempts": c, "makes": made_by_zone.get(z, 0),
                        "fg_pct": _pct(made_by_zone.get(z, 0), c)} for z, c in sorted(zones.items(), key=lambda kv: -kv[1])],
        "turnovers": {"count": len(turnovers), "rate_pct": _pct(len(turnovers), len(off)), "by_type": to_types},
        "transition_vs_halfcourt": {"transition": len(transition), "half_court": len(off) - len(transition)},
        "special_situations": specials,
    }

    # ── Section 2: our players ──
    shooters, handlers = {}, {}
    for e in off:
        s = _extra(e).get("shooter_jersey")
        if s:
            d = shooters.setdefault(str(s), {"attempts": 0, "makes": 0, "zones": {}})
            d["attempts"] += 1
            if _made(_extra(e).get("shot_result")):
                d["makes"] += 1
            z = _extra(e).get("shot_zone")
            if z:
                d["zones"][z] = d["zones"].get(z, 0) + 1
        h = _extra(e).get("ball_handler_jersey")
        if h:
            handlers[str(h)] = handlers.get(str(h), 0) + 1
    players_off = {
        "shooters": [{"jersey": k, **v, "fg_pct": _pct(v["makes"], v["attempts"])}
                     for k, v in sorted(shooters.items(), key=lambda kv: -kv[1]["attempts"])],
        "initiators": _rank(handlers),
    }

    # ── Section 3: our defense + foul trouble ──
    d_points = sum(_poss_points(_extra(e).get("result")) for e in deff)  # rarely set; opp shot zones drive it
    allowed_zones, allowed_made = {}, {}
    fouls = {}
    set_perf: Dict[str, list] = {}
    for e in deff:
        x = _extra(e)
        z = x.get("shot_zone_allowed")
        if z:
            allowed_zones[z] = allowed_zones.get(z, 0) + 1
        f = x.get("fouled_by_jersey")
        if f:
            fouls[str(f)] = fouls.get(str(f), 0) + 1
        s = x.get("defensive_set")
        if s:
            set_perf.setdefault(s, []).append(e)
    foul_trouble = [{"jersey": k, "fouls": v} for k, v in sorted(fouls.items(), key=lambda kv: -kv[1]) if v >= 3]
    defense = {
        "possessions": len(deff),
        "shot_zones_allowed": _rank(allowed_zones),
        "defensive_sets": [{"set": s, "possessions": len(v)} for s, v in
                           sorted(set_perf.items(), key=lambda kv: -len(kv[1]))],
        "foul_trouble": foul_trouble,
        "all_fouls": [{"jersey": k, "fouls": v} for k, v in sorted(fouls.items(), key=lambda kv: -kv[1])],
    }

    # ── Section 4: opponent players ──
    opp_shooters, opp_feeders = {}, {}
    for e in deff:
        x = _extra(e)
        s = x.get("opp_shooter")
        if s:
            d = opp_shooters.setdefault(str(s), {"shots": 0, "zones": {}})
            d["shots"] += 1
            z = x.get("shot_zone_allowed")
            if z:
                d["zones"][z] = d["zones"].get(z, 0) + 1
        h = x.get("opp_ball_handler")
        if h:
            opp_feeders[str(h)] = opp_feeders.get(str(h), 0) + 1
    players_opp = {
        "shooters": [{"jersey": k, **v} for k, v in sorted(opp_shooters.items(), key=lambda kv: -kv[1]["shots"])],
        "primary_feeders": _rank(opp_feeders),
    }

    return {"offense": offense, "players_offense": players_off,
            "defense": defense, "players_opponent": players_opp,
            "special_situations": specials, "momentum": _score_momentum(plays, "half")}


def _special_situations(plays) -> Dict[str, Any]:
    out: Dict[str, Any] = {"blob": 0, "slob": 0, "ato": 0, "late_game": 0}
    for e in plays:
        x = _extra(e)
        ss = _rp(x.get("special_situation")) or _rp(x.get("ball_entry"))
        if "blob" in ss:
            out["blob"] += 1
        elif "slob" in ss:
            out["slob"] += 1
        elif "ato" in ss:
            out["ato"] += 1
        if x.get("late_game"):
            out["late_game"] += 1
    return out


# ── shared: score & momentum (Section 8) ─────────────────────────────────────
def _score_momentum(plays, period_key: str) -> Dict[str, Any]:
    by_period: Dict[str, Dict[str, int]] = {}
    last = {"us": 0, "them": 0}
    for e in plays:
        x = _extra(e)
        p = str(x.get(period_key) or "?")
        us, them = _int(x.get("score_us")), _int(x.get("score_them"))
        cell = by_period.setdefault(p, {"us": 0, "them": 0})
        cell["us"], cell["them"] = max(cell["us"], us), max(cell["them"], them)
        last = {"us": max(last["us"], us), "them": max(last["them"], them)}
    poss_counts: Dict[str, int] = {}
    for e in plays:
        poss = _rp(_extra(e).get("possession")) or ("them" if e.side == "defense" else "us")
        poss_counts[poss] = poss_counts.get(poss, 0) + 1
    return {"by_period": by_period, "final_in_scope": last, "possession_play_counts": poss_counts}


# ── coaching points (Section 7) ──────────────────────────────────────────────
def _coaching_points(tendency_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    # The worker already computed collect_flagged_plays into coach_flagged_plays.
    return tendency_summary.get("coach_flagged_plays") or []


# ── season baseline (Section 9) ──────────────────────────────────────────────
def compute_season_baseline(sport: str, season_events, prior_game_count: int,
                            config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Headline rates across the team's PRIOR live games, for the trend comparison.
    Only meaningful with 3+ prior games (spec: 'activates after 3+ games logged')."""
    if prior_game_count < 3 or not season_events:
        return None
    if sport == "basketball":
        s = compute_basketball_stats(season_events, config)
        return {"games": prior_game_count,
                "points_per_possession": s["offense"]["points_per_possession"],
                "turnover_rate_pct": s["offense"]["turnovers"]["rate_pct"]}
    s = compute_football_stats(season_events, config)
    return {"games": prior_game_count,
            "yards_per_play": s["offense"]["yards_per_play"],
            "run_ypc": s["offense"]["run"]["ypc"],
            "third_down_pct": s["offense"]["third_down"]["pct"],
            "yards_per_play_allowed": s["defense"]["yards_per_play_allowed"]}


# ── section specs ────────────────────────────────────────────────────────────
def _football_spec(scope_label: str, has_season: bool) -> List[Dict[str, str]]:
    S = [
        ("Section 1: Offensive Summary", "tendency",
         "Use stats.offense. Lead with total plays, total yards, and yards_per_play. Then bullets: run/pass split "
         "(run_pass_ratio) with run ypc and pass completions/ypa; 3rd-down conversion (attempts/conversions/pct); "
         "red-zone (trips_plays, touchdowns); the formations list ranked by yards (name the most productive); and "
         "the second_and_long / third_and_short run-vs-pass tendencies. Close with our scoring plays if any."),
        ("Section 2: Player Tendencies: Our Offense", "run",
         "Use stats.players_offense. Bullet the top ball_carriers (carries, yards, ypc, their top gaps), then top "
         "targets (targets, catches, yards, top routes), then passers (completions/attempts, yards). Finally, if "
         "unused_roster is non-empty, list those jersey numbers as 'not yet involved: get them a touch'."),
        ("Section 3: Defensive Summary", "defense",
         "Use stats.defense. Lead with plays defended, yards_allowed, yards_per_play_allowed. Bullets: what the "
         "opponent ran most (opp_formations, opp_play_types, opp_run_gaps); which of our fronts held vs bled "
         "(fronts, ranked by ypp_allowed); 3rd-down conversions allowed; and pressure (blitzes, avg yards when "
         "blitzing). Flag any repeatedly exploited formation or gap."),
        ("Section 4: Player Tendencies: Opponent", "tendency",
         "Use stats.players_opponent. Bullet their top ball_carriers and top targets (with vs_coverage: e.g. "
         "'their #11 targeted 7x, 5 vs our Cover 3') and top routes. Name their primary threat and give ONE matchup "
         "call (bracket / man / rotate a safety). If empty, say opponent jersey numbers weren't logged this half."),
        ("Section 5: Special Teams Summary", "special_teams",
         "Use stats.special_teams.by_unit. One bullet per unit: count, the result breakdown, and avg_yards. Flag "
         "any outsized play (long return, block, missed FG). If no special-teams plays were logged, say so in one line."),
        ("Section 6: Top 3 Adjustments", "red_zone",
         "THE POINT OF THE REPORT. Exactly three concrete, callable adjustments for the second half, each tied to a "
         "specific number from the sections above and written the way a coordinator says it to the position group. "
         "Example voice: 'We've run A-gap on 11 of 14 first downs and they've keyed it: open the third quarter "
         "with a B-gap counter or a keeper to reset the box.' Number them 1-3."),
        ("Section 7: Coaching Points", "tendency",
         "Use stats.coaching_points (plays the staff flagged live). One bullet each: '**[clock/quarter]: [tag]**' "
         "then the coach's note VERBATIM. If empty, say no plays were flagged this half."),
        ("Section 8: Score & Momentum", "tendency",
         "Use stats.offense.momentum / stats.momentum. Give the score by period (by_period), estimate time of "
         "possession from possession_play_counts (more plays = more clock), note who scored last, and describe the "
         "momentum going into the break in one or two lines."),
    ]
    if has_season:
        S.append(("Section 9: Season Trend Comparison", "tendency",
                  "Use stats.season_baseline (this team's averages across prior games) vs this game's stats. Bullet "
                  "each headline rate: tonight vs season average, and flag where tonight is well above or below the "
                  "baseline (e.g. 'inside-run ypc 2.1 tonight vs 4.2 season: the run game is off')."))
    return [{"heading": h, "insight_type": it, "instructions": ins} for h, it, ins in S]


def _basketball_spec(scope_label: str, has_season: bool, foul_trouble: bool) -> List[Dict[str, str]]:
    S = []
    if foul_trouble:
        S.append(("⚠ FOUL TROUBLE ALERT", "red_zone",
                  "Use stats.defense.foul_trouble: our players with 3+ fouls. Put this FIRST and make it loud: name "
                  "each jersey and foul count and the substitution/scheme implication for the second half."))
    S += [
        ("Section 1: Offensive Summary", "tendency",
         "Use stats.offense. Lead with points, possessions, and points_per_possession. Bullets: shot_zones ranked "
         "by attempts with fg_pct (name where we're scoring and where we're missing); turnover count/rate/by_type; "
         "transition vs half_court; and special_situations (blob/slob/ato) counts."),
        ("Section 2: Player Tendencies: Our Offense", "tendency",
         "Use stats.players_offense. Bullet shooters (attempts, makes, fg_pct, their zones) and initiators (who "
         "starts our possessions). Name who's hot and who's forcing it."),
        ("Section 3: Defensive Summary", "defense",
         "Use stats.defense. Lead with possessions defended and the shot_zones_allowed the opponent is hitting. "
         "Bullets: which of our defensive_sets we've leaned on; zones we're giving up; and our overall foul count "
         "(all_fouls). If foul_trouble exists it was already alerted above: reference it."),
        ("Section 4: Player Tendencies: Opponent", "tendency",
         "Use stats.players_opponent. Bullet their shooters (shots, zones) and primary_feeders (who they run "
         "offense through). Name their go-to scorer and the ONE defensive assignment to make. If empty, say opponent "
         "numbers weren't logged."),
        ("Section 5: Special Situations", "tendency",
         "Use stats.special_situations. Report BLOB/SLOB/ATO counts and late_game possessions and their outcomes. "
         "If none were logged, say so in one line."),
        ("Section 6: Top 3 Adjustments", "red_zone",
         "THE POINT OF THE REPORT. Exactly three concrete second-half adjustments, each tied to a specific number "
         "above, in a coordinator's voice to the team. Number them 1-3."),
        ("Section 7: Coaching Points", "tendency",
         "Use stats.coaching_points. One bullet each with the coach's note VERBATIM. If empty, say none were flagged."),
        ("Section 8: Score & Momentum", "tendency",
         "Use stats.momentum. Score by half (by_period), any scoring run and who's carrying it, and the momentum "
         "into the break."),
    ]
    if has_season:
        S.append(("Section 9: Season Trend Comparison", "tendency",
                  "Use stats.season_baseline vs this game. Bullet points-per-possession and turnover rate tonight vs "
                  "the season average, and flag meaningful gaps."))
    return [{"heading": h, "insight_type": it, "instructions": ins} for h, it, ins in S]


# ── entry point ──────────────────────────────────────────────────────────────
async def generate_live_game_sections(
    sport: str,
    events,
    params: Dict[str, Any],
    tendency_summary: Dict[str, Any],
    is_trial: bool = False,
    season_events=None,
    prior_game_count: int = 0,
) -> List[Dict[str, Any]]:
    """Build the 9-section halftime/full-game report from the logged plays."""
    plays, meta = _split_plays(events)
    config = _extra(meta) if meta else {}
    scope = _rp(params.get("scope")) or "full"
    scope_label = "Halftime" if scope == "halftime" else "Full Game"

    if len([e for e in plays]) < 3:
        return [{
            "heading": f"{scope_label} Report: Not Enough Plays Yet",
            "insight_type": "tendency",
            "body": (f"Only {len(plays)} play(s) were logged in scope. Log a few more, then generate the "
                     f"{scope_label.lower()} report again."),
        }]

    if sport == "basketball":
        stats = compute_basketball_stats(events, config)
        foul_trouble = bool(stats["defense"]["foul_trouble"])
        season = compute_season_baseline(sport, season_events, prior_game_count, config)
        if season:
            stats["season_baseline"] = season
        stats["coaching_points"] = _coaching_points(tendency_summary)
        spec = _basketball_spec(scope_label, bool(season), foul_trouble)
    else:
        stats = compute_football_stats(events, config)
        season = compute_season_baseline(sport, season_events, prior_game_count, config)
        if season:
            stats["season_baseline"] = season
        stats["coaching_points"] = _coaching_points(tendency_summary)
        spec = _football_spec(scope_label, bool(season))

    team = config.get("team_name") or "Us"
    opponent = config.get("opponent") or "the opponent"
    section_outline = "\n".join(
        f'{i+1}. "{s["heading"]}" (insight_type: "{s["insight_type"]}")\n   Instructions: {s["instructions"]}'
        for i, s in enumerate(spec))

    prompt = f"""Sport: {sport}
Report: {scope_label} live-game report: {team} vs {opponent}
This is OUR team's report: offense = our offense, defense = our defense.

COMPUTED STATS (every number here was counted by code: cite them, never invent):
{json.dumps(stats, indent=2, default=str)}

Write the {scope_label.lower()} report as a JSON array. Each element: {{"heading": "...", "insight_type": "...", "body": "..."}}.

SECTIONS (write every one, in this exact order, keep the exact headings):
{section_outline}

BODY FORMAT:
- Each body = ONE short coordinator lead sentence, a blank line, then BULLET POINTS starting with "- ".
- One idea per bullet, one sentence, with the count next to every percentage.
- Bold key numbers and calls with **double asterisks**.
- Talk to the head coach and players, not a spreadsheet.

Return ONLY the JSON array, nothing else."""

    message = await client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT_LIVE,
        messages=[{"role": "user", "content": prompt}],
    )
    sections = _parse_report_sections(_first_text(message))
    if is_trial:
        sections.append({
            "heading": "Trial Report",
            "insight_type": "tendency",
            "body": "This is a trial report. Upgrade at coachlenz.com to unlock full reports and exports.",
        })
    return sections
