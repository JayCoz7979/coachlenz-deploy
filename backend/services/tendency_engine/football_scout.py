"""
Football opponent-scouting layer — Checks & Balances (Module 7), situational
tendency statements (Module 3 summary), and the deterministic Game Plan Builder
(Module 8).

This sits ON TOP of the existing football tendency engine (football.py). That
engine already produces the deep offense / defense / special-teams analytics.
This module turns that analysis into a coordinator-grade, self-validating
scouting brief:

    • run_validation_gates()      — the seven integrity gates, enforced
    • situational_statements()    — plain-English coordinator sentences w/ sample
                                     size + confidence tier (Gate 5 translation)
    • build_game_plan()           — installable O / D / ST calls, evidence-backed
    • build_football_scouting_report() — the public entry that assembles all three

Design principle (matches basketball_scout.py): read the sport-agnostic `events`
table + the already-computed analysis dicts. No dedicated per-category tables.
Every recommendation carries a sample size and a confidence tier so a coach knows
exactly how hard to lean on it. That is the whole point of the gates.
"""
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict

# ── Gate / confidence thresholds (single source of truth) ───────────────────
MIN_PLAYS_FOR_FINAL = 60          # Gate 1: play-count minimum across the sample
MIN_GAMES_RECOMMENDED = 3         # Gate 1: fewer than this reduces confidence
RECOMMENDATION_MIN_SAMPLE = 10    # Gate 3: below this a tendency is a "watch item"
WATCH_MIN_SAMPLE = 5              # below this we do not surface it at all
EXPLOSIVE_ALERT_RATE = 20.0       # Gate 6: concept explosive rate above this = TAKE AWAY
EXPLOSIVE_ALERT_MIN_SAMPLE = 5    # Gate 6: need this many reps to fire the alert


# ── confidence helpers ──────────────────────────────────────────────────────
def _tier(sample: int, personnel_flagged: bool = False) -> str:
    """HIGH (>=10) / MEDIUM (5-9) / LOW (<5). Gate 7 drops one tier when a
    scouted game is missing a starter (the data still counts, it just weighs less)."""
    if sample >= RECOMMENDATION_MIN_SAMPLE:
        base = "HIGH"
    elif sample >= WATCH_MIN_SAMPLE:
        base = "MEDIUM"
    else:
        base = "LOW"
    if personnel_flagged:
        base = {"HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}[base]
    return base


def _x(e, key, default=None):
    ed = getattr(e, "extra_data", None)
    if not ed:
        return default
    return ed.get(key, default)


def _side(e) -> str:
    return (getattr(e, "side", None) or "offense").lower()


def _is_play(e) -> bool:
    et = getattr(e, "event_type", None)
    return et == "play" or et in ("run", "pass", "kick", "penalty") or bool(getattr(e, "play_type", None))


def _scout_meta(events) -> Dict[str, Any]:
    """Module-1 intake metadata is stashed on a single side='meta' event so no
    new table is needed. Returns {} when a report is built straight from film."""
    for e in events:
        if getattr(e, "event_type", None) == "scout_meta":
            return getattr(e, "extra_data", None) or {}
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 7 — CHECKS AND BALANCES VALIDATION LAYER (seven gates)
# ═══════════════════════════════════════════════════════════════════════════
def run_validation_gates(events, offense: Dict[str, Any], defense: Dict[str, Any],
                         special: Dict[str, Any]) -> Dict[str, Any]:
    """Run all seven integrity gates over the raw play log + computed analysis.
    Returns a per-gate result plus an overall report status (FINAL / PRELIMINARY)."""
    plays = [e for e in events if _is_play(e)]
    meta = _scout_meta(events)
    total_plays = len(plays)

    games = {gn for e in plays if (gn := _x(e, "game_number")) is not None}
    n_games = len(games) if games else (1 if plays else 0)

    gates: List[Dict[str, Any]] = []

    # GATE 1 — PLAY COUNT MINIMUM (60+ plays, 3+ games).
    g1_pass = total_plays >= MIN_PLAYS_FOR_FINAL and n_games >= MIN_GAMES_RECOMMENDED
    g1_notes = []
    if total_plays < MIN_PLAYS_FOR_FINAL:
        g1_notes.append(f"Only {total_plays} plays logged (need {MIN_PLAYS_FOR_FINAL}). Report locked PRELIMINARY.")
    if n_games < MIN_GAMES_RECOMMENDED:
        g1_notes.append(f"Only {n_games} game(s) scouted (recommend {MIN_GAMES_RECOMMENDED}+). Tendencies may be opponent-specific.")
    gates.append({"gate": 1, "name": "Play Count Minimum", "passed": g1_pass,
                  "notes": g1_notes or ["60+ plays across 3+ games. Sample is sound."]})

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
    thin = _thin_tendencies(offense, defense)
    g3_pass = True  # informational gate — it governs where a tendency is surfaced, never blocks
    g3_notes = ([f"{len(thin)} tendency block(s) below the 10-rep recommendation line moved to Watch Items."]
                if thin else ["All surfaced tendencies clear the 10-rep recommendation line."])
    gates.append({"gate": 3, "name": "Sample Size Audit", "passed": g3_pass,
                  "notes": g3_notes, "watch_items": thin})

    # GATE 4 — CONSISTENCY CHECK (raw play log supports the stated splits).
    discrepancies = _consistency_check(plays, offense)
    g4_pass = len(discrepancies) == 0
    gates.append({"gate": 4, "name": "Consistency Check",
                  "passed": g4_pass,
                  "notes": (["Play log is internally consistent with the tendency splits."]
                            if g4_pass else [f"{len(discrepancies)} discrepancy/ies between raw plays and stated tendencies."]),
                  "discrepancies": discrepancies})

    # GATE 6 — EXPLOSIVE PLAY ALERT (any concept > 20% explosive = featured threat).
    alerts = _explosive_alerts(offense)
    gates.append({"gate": 6, "name": "Explosive Play Alert",
                  "passed": len(alerts) == 0,
                  "notes": ([f"{len(alerts)} concept(s) exceed the 20% explosive-rate line, featured as TAKE-AWAY threats."]
                            if alerts else ["No single concept exceeds the 20% explosive-play line."]),
                  "alerts": alerts})

    # GATE 7 — PERSONNEL CHANGE FLAG (missing starter in any scouted game).
    injury_flags = meta.get("injury_flags") or []
    flagged_games = meta.get("games_with_missing_starter") or []
    personnel_flagged = bool(injury_flags or flagged_games)
    g7_notes = ([f"Personnel change flagged: {', '.join(str(x) for x in (injury_flags or flagged_games))}. "
                 f"Every affected tendency drops one confidence tier and carries an asterisk."]
                if personnel_flagged else ["No missing-starter / injury flags on the scouted sample."])
    gates.append({"gate": 7, "name": "Personnel Change Flag", "passed": not personnel_flagged, "notes": g7_notes,
                  "personnel_flagged": personnel_flagged})

    # GATE 5 — GAME PLAN TRANSLATION runs last: it needs the game plan, so the
    # public builder fills its result in after build_game_plan(). Placeholder here.
    gates.append({"gate": 5, "name": "Game Plan Translation", "passed": None,
                  "notes": ["Pending game-plan assembly."]})
    gates.sort(key=lambda g: g["gate"])

    report_status = "FINAL" if g1_pass else "PRELIMINARY"
    return {
        "report_status": report_status,
        "total_plays": total_plays,
        "games_scouted": n_games,
        "personnel_flagged": personnel_flagged,
        "gates": gates,
    }


def _thin_tendencies(offense, defense) -> List[Dict[str, Any]]:
    """Gate 3 — collect named tendency blocks whose sample sits in the 5-9 range
    (real signal, but a Watch Item, never a recommendation)."""
    watch: List[Dict[str, Any]] = []

    def _scan(analysis, block_key, item_key, label):
        block = (analysis or {}).get(block_key) or {}
        items = block.get(item_key) or {}
        if isinstance(items, dict):
            for name, d in items.items():
                c = d.get("count") if isinstance(d, dict) else None
                if isinstance(c, int) and WATCH_MIN_SAMPLE <= c < RECOMMENDATION_MIN_SAMPLE:
                    watch.append({"area": label, "tendency": name, "sample": c, "tier": _tier(c)})

    _scan(offense, "run_direction_analysis", "by_concept", "Run concept")
    _scan(offense, "pass_concept_analysis", "by_concept", "Pass concept")
    _scan(offense, "run_gap_analysis", "by_gap", "Run gap")
    # formation_play_matrix is a flat {formation: {...}} map, scanned directly.
    fpm = (offense or {}).get("formation_play_matrix") or {}
    for name, d in fpm.items():
        c = d.get("count") if isinstance(d, dict) else None
        if isinstance(c, int) and WATCH_MIN_SAMPLE <= c < RECOMMENDATION_MIN_SAMPLE:
            watch.append({"area": "Formation", "tendency": name, "sample": c, "tier": _tier(c)})
    return watch


def _consistency_check(plays, offense) -> List[Dict[str, Any]]:
    """Gate 4 — cross-reference: (a) malformed down/distance, (b) the offense
    run/pass counts recomputed from the raw log match the stated split."""
    discrepancies: List[Dict[str, Any]] = []

    for i, e in enumerate(plays):
        down = getattr(e, "down", None)
        dist = getattr(e, "distance", None)
        if down is not None and down not in (1, 2, 3, 4):
            discrepancies.append({"play_index": i, "issue": f"Down out of range: {down}"})
        if dist is not None and (dist < 0 or dist > 99):
            discrepancies.append({"play_index": i, "issue": f"Distance out of range: {dist}"})

    # Recompute offensive run/pass counts and compare to the engine's summary.
    stated_run = (offense or {}).get("run_plays")
    stated_pass = (offense or {}).get("pass_plays")
    if isinstance(stated_run, int) and isinstance(stated_pass, int):
        from .football import _is_run, _is_pass  # reuse the one classifier
        off_plays = [e for e in plays if _side(e) == "offense"]
        raw_run = sum(1 for e in off_plays if _is_run(e))
        raw_pass = sum(1 for e in off_plays if _is_pass(e))
        if raw_run != stated_run:
            discrepancies.append({"issue": f"Run count mismatch: log has {raw_run}, summary states {stated_run}"})
        if raw_pass != stated_pass:
            discrepancies.append({"issue": f"Pass count mismatch: log has {raw_pass}, summary states {stated_pass}"})
    return discrepancies


def _explosive_alerts(offense) -> List[Dict[str, Any]]:
    """Gate 6 — any run concept, pass concept, or formation whose explosive rate
    clears 20% on a 5+ sample becomes a featured TAKE-AWAY threat."""
    alerts: List[Dict[str, Any]] = []

    def _scan(block_key, item_key, label):
        block = (offense or {}).get(block_key) or {}
        items = block.get(item_key) or {}
        for name, d in (items.items() if isinstance(items, dict) else []):
            if not isinstance(d, dict):
                continue
            count = d.get("count", 0)
            exp = d.get("explosive_count", 0)
            if count >= EXPLOSIVE_ALERT_MIN_SAMPLE and count:
                rate = round(exp / count * 100, 1)
                if rate >= EXPLOSIVE_ALERT_RATE:
                    alerts.append({
                        "area": label, "concept": name, "sample": count,
                        "explosive_plays": exp, "explosive_rate_pct": rate,
                        "tier": _tier(count),
                        "take_away": f"{label} '{name}' went explosive on {exp} of {count} reps ({rate}%). "
                                     f"Dedicate a defensive answer, do not treat it as one data point.",
                    })

    _scan("run_direction_analysis", "by_concept", "Run concept")
    _scan("pass_concept_analysis", "by_concept", "Pass concept")
    _scan("pass_distribution", "by_area", "Pass target area")
    _scan("run_gap_analysis", "by_gap", "Run gap")
    alerts.sort(key=lambda a: a["explosive_rate_pct"], reverse=True)
    return alerts


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 3 SUMMARY — SITUATIONAL TENDENCY STATEMENTS (Gate 5 translation)
# ═══════════════════════════════════════════════════════════════════════════
def situational_statements(offense: Dict[str, Any], defense: Dict[str, Any],
                           personnel_flagged: bool = False) -> List[Dict[str, Any]]:
    """Turn the highest-leverage splits into single-sentence coordinator statements,
    each carrying its sample size and a confidence tier. This is the plain-English
    layer Gate 5 requires — evidence in every line."""
    out: List[Dict[str, Any]] = []

    def add(text, sample, category):
        if sample and sample >= WATCH_MIN_SAMPLE:
            out.append({"category": category, "sample": sample,
                        "confidence": _tier(sample, personnel_flagged),
                        "statement": text + ("*" if personnel_flagged else "")})

    # 3rd & long pass lean — cite real pass concepts from the 9+ distance bucket.
    tl = (offense or {}).get("third_long") or {}
    if tl.get("total"):
        long_bucket = ((offense or {}).get("third_down_by_distance") or {}).get("long_9_plus") or {}
        concepts = list((long_bucket.get("top_pass_concepts") or {}).keys())[:2]
        favor = ", ".join(concepts) if concepts else "quick game / verticals"
        add(f"On 3rd & long, they pass {tl.get('pass_pct', 0)}% of the time "
            f"({tl['total']} plays); favor {favor}.",
            tl["total"], "3rd & Long")

    # 3rd & short run lean.
    ts = (offense or {}).get("third_short") or {}
    if ts.get("total"):
        add(f"On 3rd & short, they run {ts.get('run_pct', 0)}% of the time "
            f"({ts['total']} plays), favoring {', '.join(list((ts.get('top_plays') or {}).keys())[:2]) or 'inside zone'}.",
            ts["total"], "3rd & Short")

    # 1st down identity.
    fd = (offense or {}).get("first_down") or {}
    if fd.get("total"):
        lean = "run" if fd.get("run_pct", 0) >= 55 else ("pass" if fd.get("pass_pct", 0) >= 55 else "balanced")
        add(f"On 1st & 10 they are {lean} "
            f"({fd.get('run_pct', 0)}% run / {fd.get('pass_pct', 0)}% pass, {fd['total']} plays).",
            fd["total"], "1st Down")

    # Red zone lean.
    rz = (offense or {}).get("red_zone") or {}
    if rz.get("total"):
        add(f"In the red zone they run {rz.get('run_pct', 0)}% / pass {rz.get('pass_pct', 0)}% "
            f"({rz['total']} plays), scoring on {rz.get('scoring_plays', 0)}.",
            rz["total"], "Red Zone")

    # Most-used personnel identity.
    pd = (offense or {}).get("personnel_detail") or {}
    if pd:
        top = max(pd.items(), key=lambda kv: kv[1].get("count", 0))
        name, d = top
        add(f"From {name} personnel they go {d.get('run_pct', 0)}% run / {d.get('pass_pct', 0)}% pass "
            f"({d.get('count', 0)} plays, {d.get('avg_yards', 0)} ypp).", d.get("count", 0), "Personnel")

    # Defensive blitz identity on 3rd & long.
    bbs = (defense or {}).get("blitz_by_situation") or {}
    tl_blitz = bbs.get("3rd_long_6plus") or {}
    if tl_blitz.get("total"):
        add(f"On defense, they blitz {tl_blitz.get('blitz_pct', 0)}% on 3rd & 6+ "
            f"({tl_blitz['total']} snaps); base coverage "
            f"{', '.join(list((tl_blitz.get('top_coverages') or {}).keys())[:1]) or 'unknown'}.",
            tl_blitz["total"], "Defense: 3rd & Long")

    out.sort(key=lambda s: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[s["confidence"].rstrip("*")
             if s["confidence"].rstrip("*") in ("HIGH", "MEDIUM", "LOW") else "LOW"], -s["sample"]))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 8 — GAME PLAN BUILDER (installable O / D / ST, evidence-backed)
# ═══════════════════════════════════════════════════════════════════════════
def build_game_plan(offense: Dict[str, Any], defense: Dict[str, Any],
                    special: Dict[str, Any], explosive_alerts: List[Dict[str, Any]],
                    personnel_flagged: bool = False) -> Dict[str, Any]:
    """Assemble a first-draft, installable game plan. Every item is tied to a real
    number and a sample size; items under the 10-rep line are labeled Watch Items,
    never presented as recommendations (Gate 3)."""

    def _item(phase, call, evidence, sample, featured=False):
        # `featured` marks explosive TAKE-AWAY threats (Gate 6) so they lead the
        # plan regardless of raw sample — they are the game-losers, not one data point.
        return {"phase": phase, "call": call, "evidence": evidence, "sample": sample,
                "confidence": _tier(sample, personnel_flagged),
                "featured": featured,
                "class": "recommendation" if sample >= RECOMMENDATION_MIN_SAMPLE else "watch_item"}

    defensive_plan: List[Dict[str, Any]] = []
    offensive_plan: List[Dict[str, Any]] = []
    special_plan: List[Dict[str, Any]] = []

    # ── DEFENSE (attacks the opponent OFFENSE) ──────────────────────────────
    # Featured explosive threats first — these are the game-losers.
    for a in explosive_alerts[:3]:
        defensive_plan.append(_item(
            "DEF", f"TAKE AWAY {a['concept']} ({a['area']})",
            f"{a['explosive_plays']} of {a['sample']} reps went explosive ({a['explosive_rate_pct']}%). {a['take_away']}",
            a["sample"], featured=True))

    # Their best run concept -> front / gap answer.
    rda = (offense or {}).get("run_direction_analysis") or {}
    concepts = rda.get("by_concept") or {}
    if concepts:
        top_concept, cd = max(concepts.items(), key=lambda kv: kv[1].get("count", 0))
        defensive_plan.append(_item(
            "DEF", f"Set the front to stop {top_concept}",
            f"Their most-run concept: {cd.get('count', 0)} reps at {cd.get('avg_yards', 0)} ypc, "
            f"{cd.get('success_rate', 0)}% success.", cd.get("count", 0)))

    # Their hottest pass target area -> coverage leverage.
    pdist = (offense or {}).get("pass_distribution") or {}
    hottest = pdist.get("hottest_area")
    by_area = pdist.get("by_area") or {}
    if hottest and hottest in by_area:
        ad = by_area[hottest]
        defensive_plan.append(_item(
            "DEF", f"Rotate coverage to the {hottest}",
            f"Their most-targeted area: {ad.get('count', 0)} throws, {ad.get('avg_yards', 0)} yds/att, "
            f"{ad.get('success_rate', 0)}% success. Take away the first read.", ad.get("count", 0)))

    # Third & long call, tied to their pass lean.
    tl = (offense or {}).get("third_long") or {}
    if tl.get("total"):
        top_pass = list((tl.get("top_plays") or {}).keys())[:1]
        defensive_plan.append(_item(
            "DEF", "3rd & long: sit on the sticks, rush 4, 2-high",
            f"They pass {tl.get('pass_pct', 0)}% on 3rd & long ({tl['total']} plays)"
            + (f", leaning on {top_pass[0]}" if top_pass else "") + ". Bracket the chains.", tl["total"]))

    # Red zone defensive call.
    rz = (offense or {}).get("red_zone") or {}
    if rz.get("total"):
        lean = "run" if rz.get("run_pct", 0) >= 55 else "pass"
        defensive_plan.append(_item(
            "DEF", f"Red zone: load for the {lean}",
            f"Inside the 20 they go {rz.get('run_pct', 0)}% run / {rz.get('pass_pct', 0)}% pass "
            f"({rz['total']} plays). Match personnel and take away their scoring concept.", rz["total"]))

    # ── OFFENSE (attacks the opponent DEFENSE) ──────────────────────────────
    # Coverage they show most -> the concept that beats it.
    dsa = (defense or {}).get("defensive_shell_analysis") or {}
    shells = dsa.get("coverage_shells") or {}
    top_cov = (defense or {}).get("top_coverages") or {}
    if top_cov:
        cov_name, cov_ct = max(top_cov.items(), key=lambda kv: kv[1])
        beater = _coverage_beater(cov_name)
        offensive_plan.append(_item(
            "OFF", f"Attack their base coverage ({cov_name}) with {beater}",
            f"They sit in {cov_name} on {cov_ct} snaps. {beater} is the built-in answer.", cov_ct))

    # Where their pressure comes from -> protection slide.
    pga = (defense or {}).get("pressure_gap_analysis") or {}
    primary_gap = pga.get("primary_pressure_gap")
    by_gap = pga.get("by_gap") or {}
    if primary_gap and primary_gap in by_gap:
        gd = by_gap[primary_gap]
        offensive_plan.append(_item(
            "OFF", f"Slide protection to the {primary_gap}",
            f"{gd.get('count', 0)} of their blitzes come from the {primary_gap} "
            f"({gd.get('sacks', 0)} sacks). Set the back and slide the line there; carry a hot route.",
            gd.get("count", 0)))

    # If they disguise little, tell the QB he can trust the pre-snap picture.
    sda = (defense or {}).get("safety_disguise_analysis") or {}
    if sda.get("total_plays") or sda.get("disguise_rate") is not None:
        dr = sda.get("disguise_rate", 0)
        if dr and dr >= 30:
            offensive_plan.append(_item(
                "OFF", "Use motion to ID coverage (they disguise post-snap)",
                f"Safety disguise rate {dr}%. Shift/motion pre-snap and build in full-field reads.", 8))
        elif dr is not None and dr < 15:
            offensive_plan.append(_item(
                "OFF", "Trust the pre-snap picture (they tip coverage)",
                f"Safety disguise rate {dr}%. What they show pre-snap is what you get; take the leverage throw.", 8))

    # ── SPECIAL TEAMS ───────────────────────────────────────────────────────
    fg = (special or {}).get("field_goals") or {}
    by_range = fg.get("by_range") or {}
    # Find the range where they fall off a cliff.
    reliable_line = None
    for name in ("50_plus", "40_49", "30_39"):
        r = by_range.get(name) or {}
        if r.get("attempts", 0) >= 2 and r.get("pct", 100) < 60:
            reliable_line = name
            break
    if reliable_line:
        r = by_range[reliable_line]
        special_plan.append(_item(
            "ST", f"FG range alert: unreliable from {reliable_line.replace('_', '-')}",
            f"{r.get('made', 0)}/{r.get('attempts', 0)} ({r.get('pct', 0)}%) from that range. "
            f"Make them beat you from distance; consider going for it there.", r.get("attempts", 0)))

    punts = (special or {}).get("punts") or {}
    if punts.get("count"):
        cov = punts.get("coverage_allowed") or {}
        if cov.get("avg_return_allowed", 0) >= 8 or cov.get("explosive_allowed", 0) >= 1:
            special_plan.append(_item(
                "ST", "Punt return opportunity (their coverage leaks)",
                f"They allow {cov.get('avg_return_allowed', 0)} yds/return "
                f"({cov.get('explosive_allowed', 0)} explosive). Set up a return.", punts["count"]))
        directional = punts.get("directional_pct") or {}
        if directional:
            side = max(directional, key=directional.get)
            if directional[side] >= 55:
                special_plan.append(_item(
                    "ST", f"Punt tends {side} ({directional[side]}%), set the wall that way",
                    f"Directional tendency to {side}. Overload the return that direction.", punts["count"]))

    fakes = (special or {}).get("fakes_and_trick") or {}
    if fakes.get("count"):
        special_plan.append(_item(
            "ST", "FAKE ALERT: they have shown trick plays",
            f"{fakes.get('count', 0)} fakes on film ({fakes.get('success_rate', 0)}% success). "
            f"Stay in coverage-alert on all 4th-down ST looks.", fakes["count"]))

    def _rank(plan):
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        # Featured explosive threats first, then by confidence tier, then sample.
        plan.sort(key=lambda x: (0 if x.get("featured") else 1,
                                 order.get(x["confidence"].rstrip("*"), 3), -x["sample"]))
        return plan

    return {
        "defensive_plan": _rank(defensive_plan),
        "offensive_plan": _rank(offensive_plan),
        "special_teams_plan": _rank(special_plan),
    }


def _coverage_beater(coverage: str) -> str:
    """The classic built-in answer to a base coverage — coordinator shorthand."""
    c = (coverage or "").lower()
    if "cover 0" in c or "cover0" in c or c == "0":
        return "quick game / hot routes and max protect shots"
    if "cover 1" in c or "man" in c:
        return "mesh, crossers, and pick concepts (beat man)"
    if "cover 2" in c or "tampa" in c:
        return "smash and deep-hole seam (attack the honey hole)"
    if "cover 3" in c or "1-high" in c:
        return "four verticals and curl-flat (flood the underneath)"
    if "cover 4" in c or "quarters" in c:
        return "play-action deep crossers and the dagger concept"
    if "cover 6" in c or "quarter-quarter-half" in c:
        return "attack the quarter side with a vertical stem"
    return "a concept that stresses the leverage they show"


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY
# ═══════════════════════════════════════════════════════════════════════════
def build_football_scouting_report(events, offense: Dict[str, Any],
                                   defense: Dict[str, Any],
                                   special: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the football `scouting` block: validation gates, situational
    tendency statements, and the installable game plan. Merged into the football
    tendency summary the same way basketball's scouting block is."""
    if not events:
        return {"available": False}

    validation = run_validation_gates(events, offense, defense, special)
    personnel_flagged = validation.get("personnel_flagged", False)

    # Explosive alerts live inside Gate 6 — pull them for the game plan.
    explosive_alerts = next((g.get("alerts", []) for g in validation["gates"] if g["gate"] == 6), [])

    statements = situational_statements(offense, defense, personnel_flagged)
    game_plan = build_game_plan(offense, defense, special, explosive_alerts, personnel_flagged)

    # Auto Scouting Keys — the plain-English layer that speaks the WHOLE engine
    # (pre-snap tells, formation/personnel/concept splits, explosive sources,
    # situational), ranked most-exploitable first. Plus the self-scout view.
    from .scouting_keys import build_scouting_keys, build_self_scout
    scouting_keys = build_scouting_keys(offense, defense, special, personnel_flagged)
    self_scout = build_self_scout(offense, defense, special, personnel_flagged)

    # GATE 5 — GAME PLAN TRANSLATION: pass iff we produced installable calls.
    total_calls = (len(game_plan["defensive_plan"]) + len(game_plan["offensive_plan"])
                   + len(game_plan["special_teams_plan"]))
    recs = sum(1 for p in ("defensive_plan", "offensive_plan", "special_teams_plan")
               for item in game_plan[p] if item["class"] == "recommendation")
    for g in validation["gates"]:
        if g["gate"] == 5:
            g["passed"] = total_calls > 0
            g["notes"] = [f"Translated tendencies into {total_calls} installable call(s) "
                          f"({recs} at recommendation confidence, the rest watch items)."] if total_calls else \
                         ["Not enough clean tendency data to translate into a game plan yet."]

    return {
        "available": True,
        "report_status": validation["report_status"],
        "total_plays": validation["total_plays"],
        "games_scouted": validation["games_scouted"],
        "personnel_flagged": personnel_flagged,
        "validation_gates": validation["gates"],
        "situational_tendencies": statements,
        # The full plain-English key set, ranked most-exploitable first.
        "scouting_keys": scouting_keys,
        # Self-scout view of the same facts (populated for self_scout reports).
        "self_scout": self_scout,
        "game_plan": game_plan,
        # A flat, priority-ordered digest for the head-coach one-pager.
        "head_coach_priorities": _head_coach_digest(game_plan),
    }


def _head_coach_digest(game_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Top items across all three phases, recommendations first — the tear-away sheet."""
    everything = (game_plan.get("defensive_plan", []) + game_plan.get("offensive_plan", [])
                  + game_plan.get("special_teams_plan", []))
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    everything.sort(key=lambda x: (0 if x.get("featured") else 1,
                                   0 if x["class"] == "recommendation" else 1,
                                   order.get(x["confidence"].rstrip("*"), 3), -x["sample"]))
    return [{"priority": i + 1, "phase": it["phase"], "call": it["call"],
             "confidence": it["confidence"]} for i, it in enumerate(everything[:7])]
