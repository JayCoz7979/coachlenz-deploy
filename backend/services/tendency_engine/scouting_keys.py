"""
Auto Scouting Keys — the plain-English tendency layer.

The football tendency engine (football.py) already computes deep analytics:
the pre-snap tell matrix (formation + motion + down + distance -> run/pass %),
formation and personnel splits, run/pass concepts, explosive sources, and every
situational bucket. But almost none of that gets *spoken*. football_scout.py only
turns about six hard-coded splits into sentences.

This module speaks the whole engine. It reads the already-computed offense /
defense / special dicts and emits a single ranked list of coordinator-grade keys,
each a one-liner carrying its sample size, a confidence tier, a lopsidedness
"strength" score, and the exploit (what to do about it). The most exploitable
keys float to the top. This is the coach's literal ask:

    "Hey Coach, they run Power 75% from this formation."
    "Every time they're in trips on 3rd-and-medium they're looking for this concept."

The SAME facts, reframed, power self-scout: what YOU are giving away, which of your
concepts are actually winning, and where you are hurting yourself. A tendency is a
tendency; only the voice changes (exploit it vs. fix it).

Design matches the rest of the engine: read the already-computed dicts, no new
tables, a sample size and confidence tier on every line so a coach knows exactly
how hard to lean on it.
"""
from typing import List, Dict, Any, Optional
from collections import Counter

# Confidence thresholds — single source of truth, matches football_scout.py.
RECOMMENDATION_MIN_SAMPLE = 10   # HIGH confidence line
WATCH_MIN_SAMPLE = 5             # below this we do not surface a key at all
STRONG_LEAN = 65.0               # a run/pass split this lopsided is a real key
DOMINANT_LEAN = 75.0             # "they hang their hat on it" territory
EXP_MIN = 3                      # min explosive plays before an explosive-source key fires
MAX_KEYS = 20                    # keep the report scannable; rank and cap


def _tier(sample: int, personnel_flagged: bool = False) -> str:
    """HIGH (>=10) / MEDIUM (5-9) / LOW (<5). Drops one tier when a scouted game
    was missing a starter (Gate 7) — the data still counts, it just weighs less."""
    if sample >= RECOMMENDATION_MIN_SAMPLE:
        base = "HIGH"
    elif sample >= WATCH_MIN_SAMPLE:
        base = "MEDIUM"
    else:
        base = "LOW"
    if personnel_flagged:
        base = {"HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}[base]
    return base


def _lean_strength(pct: float) -> float:
    """How far a split is from a coin flip. 50% -> 0, 100% -> 100."""
    return round(abs(pct - 50) * 2, 1)


def _down_name(down: Optional[int]) -> str:
    return {1: "1st down", 2: "2nd down", 3: "3rd down", 4: "4th down"}.get(down, "unknown down")


def _lean(run_pct: float, pass_pct: float) -> str:
    return "run" if run_pct >= pass_pct else "pass"


# ═══════════════════════════════════════════════════════════════════════════
# OPPONENT KEYS
# ═══════════════════════════════════════════════════════════════════════════
def build_scouting_keys(offense: Dict[str, Any], defense: Dict[str, Any],
                        special: Dict[str, Any],
                        personnel_flagged: bool = False) -> List[Dict[str, Any]]:
    """Ranked, plain-English opponent keys drawn from the FULL analytics. Every key:
    {category, statement, sample, confidence, strength, exploit}. Ranked most
    exploitable first (lopsidedness, then sample). Keys under 5 reps are dropped."""
    offense = offense or {}
    defense = defense or {}
    special = special or {}
    keys: List[Dict[str, Any]] = []

    def add(category: str, statement: str, sample: int, strength: float,
            exploit: str, featured: bool = False):
        # Featured game-losers (explosive/fake threats) surface even below the
        # 5-rep floor — a small sample of chunk plays is still a threat to flag.
        if not sample or (sample < WATCH_MIN_SAMPLE and not featured):
            return
        star = "*" if personnel_flagged else ""
        keys.append({
            "category": category,
            "statement": statement + star,
            "sample": sample,
            "confidence": _tier(sample, personnel_flagged),
            "strength": round(strength, 1),
            "exploit": exploit,
            "featured": featured,
        })

    # ── Pre-snap tells: the centerpiece. formation + motion + down + distance -> ──
    #    lopsided run/pass with the most-common concept. This IS the coach's dream.
    for t in (offense.get("pre_snap_tells") or [])[:8]:
        total = t.get("count", 0)
        run_pct, pass_pct = t.get("run_pct", 0), t.get("pass_pct", 0)
        lean_pct = max(run_pct, pass_pct)
        if lean_pct < STRONG_LEAN:
            continue
        lean = _lean(run_pct, pass_pct)
        motion = "with motion" if t.get("motion") else "no motion"
        concept = t.get("most_common_concept")
        # Suppress a "concept" that is just the generic play type ("run"/"pass").
        if concept and str(concept).lower() in ("run", "pass"):
            concept = None
        stmt = (f"From {t.get('formation')} ({motion}) on {_down_name(t.get('down'))} "
                f"{t.get('distance_bucket', '')}, they {lean} {lean_pct}% ({total} reps)")
        if concept:
            stmt += f", favoring {concept}"
        stmt += "."
        exploit = (f"Key the {t.get('formation')} look in this down/distance and sit on the {lean}"
                   + (f" ({concept})" if concept else "") + ".")
        add("Pre-Snap Tell", stmt, total, _lean_strength(lean_pct), exploit,
            featured=lean_pct >= DOMINANT_LEAN)

    # ── Formation identity: per-formation run/pass lean + go-to play. ──
    fpm = offense.get("formation_play_matrix") or {}
    for form, d in list(fpm.items())[:6]:
        total = d.get("count", 0)
        lean_pct = max(d.get("run_pct", 0), d.get("pass_pct", 0))
        if lean_pct < STRONG_LEAN:
            continue
        lean = _lean(d.get("run_pct", 0), d.get("pass_pct", 0))
        top = list((d.get("top_plays") or {}).keys())[:1]
        go_to = f", go-to: {top[0]}" if top else ""
        add("Formation Tendency",
            f"Out of {form} they {lean} {lean_pct}% ({total} plays, {d.get('avg_yards', 0)} ypp{go_to}).",
            total, _lean_strength(lean_pct),
            f"When they line up in {form}, expect {lean}; set your front/coverage to it.")

    # ── Personnel identity. ──
    for pers, d in list((offense.get("personnel_detail") or {}).items())[:3]:
        total = d.get("count", 0)
        lean_pct = max(d.get("run_pct", 0), d.get("pass_pct", 0))
        if lean_pct < STRONG_LEAN:
            continue
        lean = _lean(d.get("run_pct", 0), d.get("pass_pct", 0))
        add("Personnel Tendency",
            f"In {pers} personnel they {lean} {lean_pct}% ({total} plays, {d.get('avg_yards', 0)} ypp).",
            total, _lean_strength(lean_pct),
            f"Match personnel to {pers} and play the {lean}.")

    # ── Down & distance identity across every meaningful bucket. ──
    dd_buckets = [
        ("first_down", "1st & 10"),
        ("second_long", "2nd & long"), ("second_short", "2nd & short"),
        ("third_long", "3rd & long"), ("third_medium", "3rd & medium"), ("third_short", "3rd & short"),
    ]
    for key, label in dd_buckets:
        d = offense.get(key) or {}
        total = d.get("total", 0)
        if not total:
            continue
        lean_pct = max(d.get("run_pct", 0), d.get("pass_pct", 0))
        if lean_pct < STRONG_LEAN:
            continue
        lean = _lean(d.get("run_pct", 0), d.get("pass_pct", 0))
        top = [p for p in (d.get("top_plays") or {}).keys() if str(p).lower() not in ("run", "pass")][:2]
        favor = f", favoring {', '.join(top)}" if top else ""
        add("Down & Distance",
            f"On {label} they {lean} {lean_pct}% ({total} plays{favor}).",
            total, _lean_strength(lean_pct),
            f"On {label}, load for the {lean}.")

    # ── Run identity: best concept + direction lean. ──
    rda = offense.get("run_direction_analysis") or {}
    by_concept = rda.get("by_concept") or {}
    if by_concept:
        top_concept, cd = max(by_concept.items(), key=lambda kv: kv[1].get("count", 0))
        total = cd.get("count", 0)
        # Strength blends how often it is called with how well it works.
        share = round(total / rda.get("total_runs", total) * 100, 1) if rda.get("total_runs") else 0
        add("Run Game",
            f"Their bread-and-butter run is {top_concept}: {total} reps, "
            f"{cd.get('avg_yards', 0)} ypc, {cd.get('success_rate', 0)}% success"
            + (f", {cd.get('explosive_count')} explosive" if cd.get("explosive_count") else "") + ".",
            total, max(_lean_strength(50 + share / 2), cd.get("success_rate") or 0),
            f"Stop {top_concept} first — it's their hat-hanger. Set the front to it.")
    if rda.get("total_runs"):
        left, right = rda.get("left_pct", 0), rda.get("right_pct", 0)
        strong = "left" if left >= right else "right"
        strong_pct = max(left, right)
        if strong_pct >= STRONG_LEAN:
            add("Run Direction",
                f"They run {strong} {strong_pct}% of the time ({rda.get('total_runs')} runs, "
                f"{rda.get('inside_pct', 0)}% inside / {rda.get('outside_pct', 0)}% outside).",
                rda.get("total_runs", 0), _lean_strength(strong_pct),
                f"Set the strength / slant your front to the {strong} side.")

    # ── Pass identity: hottest target area + top concept. ──
    pdist = offense.get("pass_distribution") or {}
    hottest = pdist.get("hottest_area")
    by_area = pdist.get("by_area") or {}
    if hottest and hottest in by_area:
        ad = by_area[hottest]
        total = ad.get("count", 0)
        add("Pass Game",
            f"Their #1 pass target is the {hottest}: {total} throws "
            f"({ad.get('pct_of_passes', 0)}% of passes), {ad.get('avg_yards', 0)} yds/att, "
            f"{ad.get('success_rate', 0)}% success.",
            total, max((ad.get("pct_of_passes") or 0) * 1.5, ad.get("success_rate") or 0),
            f"Rotate coverage to the {hottest} and take away the first read.")
    pca = (offense.get("pass_concept_analysis") or {}).get("by_concept") or {}
    if pca:
        top_pc, pcd = max(pca.items(), key=lambda kv: kv[1].get("count", 0))
        total = pcd.get("count", 0)
        add("Pass Game",
            f"Favorite pass concept: {top_pc} ({total} calls, {pcd.get('pct_of_passes', 0)}% of passes, "
            f"{pcd.get('avg_yards', 0)} yds, {pcd.get('success_rate', 0)}% success).",
            total, max((pcd.get("pct_of_passes") or 0) * 1.5, pcd.get("success_rate") or 0),
            f"Drill the defense against {top_pc}; it's their go-to dropback answer.")

    # ── Explosive sources — the game-losers. Featured to the top. ──
    en = offense.get("explosive_negative") or {}
    top_exp_form = en.get("top_explosive_formations") or {}
    if en.get("explosive_count", 0) >= EXP_MIN and top_exp_form:
        form, cnt = max(top_exp_form.items(), key=lambda kv: kv[1])
        add("Explosive Threat",
            f"{en.get('explosive_count')} explosive plays ({en.get('explosive_pct', 0)}% of snaps); "
            f"most came from {form} ({cnt}). Avg explosive gain {en.get('avg_explosive_gain', 0)} yds.",
            en.get("explosive_count", 0), 80.0,
            f"Their chunk plays cluster in {form} — get a hat on the deep threat out of that look.",
            featured=True)

    # ── Motion tell. ──
    ma = offense.get("motion_analysis") or {}
    wm = ma.get("with_motion") or {}
    if wm.get("count", 0) >= WATCH_MIN_SAMPLE and ma.get("motion_pct", 0) >= 20:
        lean_pct = max(wm.get("run_pct", 0), wm.get("pass_pct", 0))
        if lean_pct >= STRONG_LEAN:
            lean = _lean(wm.get("run_pct", 0), wm.get("pass_pct", 0))
            add("Motion Tell",
                f"When they use motion ({ma.get('motion_pct', 0)}% of snaps) they {lean} "
                f"{lean_pct}% ({wm.get('count')} plays).",
                wm.get("count", 0), _lean_strength(lean_pct),
                f"Motion is a {lean} tip — key it and trigger.")

    # ── Situational: red zone, goal line, short yardage, two-minute. ──
    rz = offense.get("red_zone") or {}
    if rz.get("total"):
        lean_pct = max(rz.get("run_pct", 0), rz.get("pass_pct", 0))
        lean = _lean(rz.get("run_pct", 0), rz.get("pass_pct", 0))
        add("Red Zone",
            f"In the red zone they {lean} {lean_pct}% ({rz.get('total')} plays), "
            f"scored on {rz.get('scoring_plays', 0)}.",
            rz.get("total", 0), _lean_strength(lean_pct),
            f"Inside the 20, load for the {lean} and match their scoring personnel.")
    gl = offense.get("goal_line") or {}
    if gl.get("total_plays"):
        lean_pct = max(gl.get("run_pct", 0), gl.get("pass_pct", 0))
        lean = _lean(gl.get("run_pct", 0), gl.get("pass_pct", 0))
        add("Goal Line",
            f"On the goal line (5 and in) they {lean} {lean_pct}% ({gl.get('total_plays')} plays), "
            f"scoring {gl.get('scoring_rate', 0)}%.",
            gl.get("total_plays", 0), _lean_strength(lean_pct),
            f"Goal line: sell out for the {lean}.")
    sy = offense.get("short_yardage") or {}
    if sy.get("total"):
        lean_pct = max(sy.get("run_pct", 0), sy.get("pass_pct", 0))
        lean = _lean(sy.get("run_pct", 0), sy.get("pass_pct", 0))
        if lean_pct >= STRONG_LEAN:
            top = list((sy.get("top_plays") or {}).keys())[:1]
            add("Short Yardage",
                f"On 3rd/4th & short they {lean} {lean_pct}% ({sy.get('total')} plays"
                + (f", {top[0]}" if top else "") + f"), {sy.get('success_rate', 0)}% success.",
                sy.get("total", 0), _lean_strength(lean_pct),
                f"Short yardage: they {lean}. Fit the gaps and squeeze.")

    # ── Defense keys: blitz tendency by situation + coverage lean. ──
    bbs = defense.get("blitz_by_situation") or {}
    for key, label in (("3rd_long_6plus", "3rd & long (6+)"), ("3rd_short_1to3", "3rd & short")):
        b = bbs.get(key) or {}
        if b.get("total") and b.get("blitz_pct", 0) >= 40:
            cov = list((b.get("top_coverages") or {}).keys())[:1]
            add("Defense: Pressure",
                f"They blitz {b.get('blitz_pct')}% on {label} ({b.get('total')} snaps"
                + (f", behind {cov[0]}" if cov else "") + ").",
                b.get("total", 0), _lean_strength(b.get("blitz_pct", 0)),
                f"Expect pressure on {label} — carry a hot route and a max-protect shot.")
    top_cov = defense.get("top_coverages") or {}
    if top_cov:
        cov_name, cov_ct = max(top_cov.items(), key=lambda kv: kv[1])
        if cov_ct >= WATCH_MIN_SAMPLE:
            add("Defense: Coverage",
                f"Their base coverage is {cov_name} ({cov_ct} snaps).",
                cov_ct, 55.0,
                f"Install the built-in beater for {cov_name} as your opening script answer.")

    # ── Special teams: FG range cliff, punt direction, fakes. ──
    fakes = (special.get("fakes_and_trick") or {})
    if fakes.get("count"):
        add("Special Teams: Alert",
            f"They have shown {fakes.get('count')} fake/trick plays on film "
            f"({fakes.get('success_rate', 0)}% success).",
            fakes.get("count", 0), 70.0,
            "Stay coverage-alert on every 4th-down and ST look.", featured=True)
    punts = special.get("punts") or {}
    directional = punts.get("directional_pct") or {}
    if punts.get("count", 0) >= WATCH_MIN_SAMPLE and directional:
        side = max(directional, key=directional.get)
        if directional[side] >= 55:
            add("Special Teams: Punt",
                f"Their punter tends {side} ({directional[side]}%, {punts.get('count')} punts).",
                punts.get("count", 0), _lean_strength(directional[side]),
                f"Set the return wall to the {side}.")

    # Rank: featured game-losers first, then by lopsidedness, then sample.
    keys.sort(key=lambda k: (0 if k["featured"] else 1, -k["strength"], -k["sample"]))
    # Renumber priority for the consumer.
    for i, k in enumerate(keys[:MAX_KEYS]):
        k["priority"] = i + 1
    return keys[:MAX_KEYS]


# ═══════════════════════════════════════════════════════════════════════════
# SELF-SCOUT — the same facts, turned on yourself
# ═══════════════════════════════════════════════════════════════════════════
def build_self_scout(offense: Dict[str, Any], defense: Dict[str, Any],
                     special: Dict[str, Any],
                     personnel_flagged: bool = False) -> Dict[str, Any]:
    """Self-scout view: what you are giving away (predictability), which of your
    concepts are actually winning, and where you are hurting yourself. Built from
    the same analytics as the opponent keys, reframed from 'exploit it' to 'fix it'."""
    offense = offense or {}
    if not offense.get("total_plays"):
        return {"available": False}

    predictability: List[Dict[str, Any]] = []

    def tip(statement: str, sample: int, strength: float, fix: str):
        if sample and sample >= WATCH_MIN_SAMPLE:
            predictability.append({
                "statement": statement, "sample": sample,
                "confidence": _tier(sample, personnel_flagged),
                "strength": round(strength, 1), "fix": fix,
            })

    # Pre-snap tips — the loudest thing you broadcast.
    for t in (offense.get("pre_snap_tells") or [])[:8]:
        total = t.get("count", 0)
        lean_pct = max(t.get("run_pct", 0), t.get("pass_pct", 0))
        if lean_pct < STRONG_LEAN:
            continue
        lean = _lean(t.get("run_pct", 0), t.get("pass_pct", 0))
        motion = "with motion" if t.get("motion") else "no motion"
        tip(f"You tip {lean} {lean_pct}% from {t.get('formation')} ({motion}) on "
            f"{_down_name(t.get('down'))} {t.get('distance_bucket', '')} ({total} reps).",
            total, _lean_strength(lean_pct),
            f"Add a counter/change-up from this exact look so {t.get('formation')} isn't a {lean} flag.")

    # Formation predictability.
    for form, d in list((offense.get("formation_play_matrix") or {}).items())[:6]:
        total = d.get("count", 0)
        lean_pct = max(d.get("run_pct", 0), d.get("pass_pct", 0))
        if lean_pct >= DOMINANT_LEAN:
            lean = _lean(d.get("run_pct", 0), d.get("pass_pct", 0))
            tip(f"{form} is a {lean} giveaway: {lean_pct}% {lean} ({total} plays).",
                total, _lean_strength(lean_pct),
                f"Balance {form} or you're telling the defense {lean} every time you show it.")

    predictability.sort(key=lambda k: (-k["strength"], -k["sample"]))

    # What's actually winning — concepts by success rate with real sample.
    winning: List[Dict[str, Any]] = []

    def win(statement: str, sample: int, success: float):
        if sample and sample >= WATCH_MIN_SAMPLE:
            winning.append({"statement": statement, "sample": sample,
                            "success_rate": success, "confidence": _tier(sample, personnel_flagged)})

    ybp = offense.get("yards_by_play_type") or {}
    for pt, d in ybp.items():
        if d.get("count", 0) >= WATCH_MIN_SAMPLE and d.get("success_rate", 0) >= 55:
            win(f"{pt} is working: {d.get('success_rate')}% success, {d.get('avg_yards', 0)} ypp "
                f"({d.get('count')} calls, {d.get('explosive_count', 0)} explosive).",
                d.get("count", 0), d.get("success_rate", 0))
    rc = (offense.get("run_direction_analysis") or {}).get("by_concept") or {}
    for concept, d in rc.items():
        if d.get("count", 0) >= WATCH_MIN_SAMPLE and d.get("success_rate", 0) >= 55:
            win(f"{concept} run is winning: {d.get('success_rate')}% success, {d.get('avg_yards', 0)} ypc "
                f"({d.get('count')} reps).", d.get("count", 0), d.get("success_rate", 0))
    winning.sort(key=lambda k: (-k["success_rate"], -k["sample"]))

    # Where you're hurting yourself.
    self_inflicted: List[Dict[str, Any]] = []
    en = offense.get("explosive_negative") or {}
    if en.get("negative_count"):
        top_neg = list((en.get("top_negative_plays") or {}).keys())[:2]
        self_inflicted.append({
            "statement": f"{en.get('negative_count')} negative plays ({en.get('negative_pct', 0)}% of snaps)"
            + (f", most on {', '.join(top_neg)}" if top_neg else "") + ".",
            "count": en.get("negative_count", 0),
        })
    results = offense.get("play_results") or {}
    penalties = sum(v for k, v in results.items() if k and "penal" in k.lower())
    if penalties:
        self_inflicted.append({"statement": f"{penalties} penalties on offense, drive killers.",
                               "count": penalties})
    turnovers = sum(v for k, v in results.items()
                    if k and any(w in k.lower() for w in ("intercept", "fumble", "turnover")))
    if turnovers:
        self_inflicted.append({"statement": f"{turnovers} turnovers on film — protect the ball.",
                               "count": turnovers})

    biggest = predictability[0]["statement"] if predictability else None
    return {
        "available": True,
        "predictability": predictability[:12],
        "winning_concepts": winning[:8],
        "self_inflicted": self_inflicted,
        "biggest_giveaway": biggest,
        "summary": (
            f"{len(predictability)} predictability flag(s), {len(winning)} winning concept(s), "
            f"{len(self_inflicted)} self-inflicted area(s)."
        ),
    }
