"""
Football concept taxonomy + deterministic concept recovery.

Concept detection (run_concept / pass_concept) is what turns a run/pass tendency
into the thing a coach actually game-plans: "Power 75% from this formation." The
vision model is asked to name the concept post-snap, but on single-camera film it
often can't, and a null concept silently drops the tendency.

This module does two jobs, from ONE source of truth:

  1. `postsnap_concept_guidance()` — the concept list WITH real recognition cues,
     injected into the post-snap detection prompt so the model classifies from
     coaching keys (pulling linemen -> Power/Counter, zone steps -> Zone) instead
     of guessing off a bare list of names.

  2. `fill_concepts(play)` — a deterministic fallback. When the model left the
     concept null, recover it: FIRST by mining the play_description the model
     already wrote ("Power right to the B-gap" -> Power), THEN from structural
     signals (gap / direction / play_type / screen subtype). Every fill records a
     confidence and a source ("model" | "description" | "signals") so the report
     stays honest about how the concept was determined. A confident model read is
     never overwritten.

HS-focused: the core concept menu a Friday-night staff actually sees, not an
exhaustive NFL install.
"""
from typing import Dict, Any, List, Optional, Tuple

# ── RUN CONCEPTS: (canonical name, recognition cue, alias keywords) ──────────
# Aliases are lowercase substrings scanned in the model's play_description.
RUN_CONCEPTS: List[Tuple[str, str, List[str]]] = [
    ("Inside Zone", "OL takes lateral zone steps play-side, double-teams to the backers, RB presses A/B gap and cuts off the first down lineman. No puller.",
     ["inside zone", "iz ", " iz", "tight zone"]),
    ("Outside Zone", "OL reaches play-side on the run, ball stretches to the perimeter, RB reads the C-gap to bounce/bang/bend. Wide 'stretch'.",
     ["outside zone", "wide zone", "stretch", "zone stretch"]),
    ("Power", "Back-side guard PULLS and kicks/leads through the hole, play-side down-blocks, a tight end or back kicks out the edge. Downhill.",
     ["power", "power o", "gap power", "qb power"]),
    ("Counter", "TWO pullers (guard kicks out, tackle/H-back wraps) with mis-direction — back takes a false step away, then downhill behind the wrap.",
     ["counter", "gt counter", "g-t", "counter trey", "buck counter"]),
    ("Trap", "A single defender is left unblocked then TRAPPED/kicked out by a pulling guard; the rest down-block. Quick-hitting interior.",
     ["trap", "mid-line trap", "wham"]),
    ("Duo", "Double-team power without a puller — two vertical double-teams, RB reads the linebacker (a downhill 'power read' look).",
     ["duo"]),
    ("Iso", "Lead back ISOLATES a linebacker through the hole, straight downhill, no pull. Classic I-back lead.",
     ["iso", "isolation", "lead iso"]),
    ("Dive", "Straight-ahead give right now, A-gap, no read, no pull — the quickest interior hit.",
     ["dive", "quick dive", "belly"]),
    ("Buck Sweep", "Both guards PULL to the perimeter, back sweeps behind them. Wing-T / pin-and-pull staple.",
     ["buck sweep", "sweep", "pin and pull", "pin-and-pull"]),
    ("Jet Sweep", "Fast motion man takes the handoff on the fly across the formation to the edge.",
     ["jet sweep", "jet", "fly sweep", "orbit"]),
    ("Toss", "Pitch/toss to the RB getting to the edge fast, tackle and TE reach or a puller leads.",
     ["toss", "pitch", "crack toss", "sweep toss"]),
    ("Zone Read", "QB reads the back-side end and keeps or gives off zone action (RPO family lives here).",
     ["zone read", "read option", "rpo", "zone-read", "read arc", "q read"]),
    ("Speed Option", "QB attacks the edge and pitches off the force defender — triple/speed option.",
     ["speed option", "triple option", "option pitch", "veer"]),
    ("Draw", "Shows pass set, then delays the give up the middle — a pass-rush counter.",
     ["draw", "qb draw", "delay draw"]),
]

# ── PASS CONCEPTS: (canonical name, recognition cue, alias keywords) ─────────
PASS_CONCEPTS: List[Tuple[str, str, List[str]]] = [
    ("Mesh", "Two crossers rub underneath at 5-6 yds (man-beater), with a sit/corner behind.",
     ["mesh"]),
    ("Smash", "Hitch/flat under a corner route — classic Cover-2 hi-lo on the corner.",
     ["smash", "hi-lo corner"]),
    ("Four Verticals", "Four receivers run vertical stems, seams bend vs the safeties.",
     ["four vert", "4 vert", "verticals", "four verticals", "seams"]),
    ("Flood", "Three routes at three levels to one side (deep-out-flat) — stretch a zone side.",
     ["flood", "sail", "three level", "3 level"]),
    ("Stick", "Quick stick/flat spacing concept — beat off/zone underneath, sit in the window.",
     ["stick", "stick-flat"]),
    ("Slant-Flat", "Slant with a flat under it — quick man/zone beater to one side.",
     ["slant-flat", "slant flat", "slant/flat", "slants"]),
    ("Curl-Flat", "Curl with a flat under it — hi-lo the flat defender.",
     ["curl-flat", "curl flat", "curl/flat", "hitch-flat"]),
    ("Y-Cross", "The Y crosses the field deep off play-action, with a shallow/dig behind it.",
     ["y-cross", "y cross", "yankee", "deep cross"]),
    ("Dagger", "Vertical clear-out over a dig/square-in behind it (dig behind the seam).",
     ["dagger", "dig behind"]),
    ("Levels", "In-breaking routes at two levels (shallow + dig) — beat man/zone middle.",
     ["levels", "in-cut levels"]),
    ("Drive", "Shallow cross with a dig behind — the West-Coast 'drive' rub.",
     ["drive concept", "shallow cross", "shallow drive"]),
    ("Snag", "Triangle: snag/spot sit, corner, flat — spacing triangle to one side.",
     ["snag", "spot", "triangle"]),
    ("PA Boot", "Play-action boot/naked — QB fakes the run and rolls, high-low the flat.",
     ["boot", "naked", "waggle", "keeper", "play action pass", "play-action boot"]),
    ("Screen", "Ball behind the LOS to a back/receiver with blockers releasing in front.",
     ["screen", "bubble", "tunnel", "jailbreak", "slip screen"]),
    ("Quick Game", "One-step hitches/quick outs — get the ball out now vs pressure/off.",
     ["hitch", "quick out", "quick game", "now route", "spacing quick"]),
]

_RUN_LOOKUP = [(name, cue, [a.strip() for a in aliases]) for name, cue, aliases in RUN_CONCEPTS]
_PASS_LOOKUP = [(name, cue, [a.strip() for a in aliases]) for name, cue, aliases in PASS_CONCEPTS]

RUN_CONCEPT_NAMES = [n for n, _, _ in RUN_CONCEPTS]
PASS_CONCEPT_NAMES = [n for n, _, _ in PASS_CONCEPTS]


# ═══════════════════════════════════════════════════════════════════════════
# 1) PROMPT GUIDANCE — the taxonomy WITH recognition cues for the vision model
# ═══════════════════════════════════════════════════════════════════════════
def postsnap_concept_guidance() -> str:
    """A prompt block that teaches the model to classify concepts from coaching
    keys, not a bare name list. Injected into the post-snap detection prompt."""
    run_lines = "\n".join(f"    - {n}: {cue}" for n, cue, _ in RUN_CONCEPTS)
    pass_lines = "\n".join(f"    - {n}: {cue}" for n, cue, _ in PASS_CONCEPTS)
    return (
        "CONCEPT CLASSIFICATION — name the concept from what the blocking/routes actually show. "
        "If the single-camera angle genuinely does not let you tell, set the concept to null and say so in "
        "blind_spot — do NOT guess. Also return concept_confidence (0-1) for your concept read.\n"
        "  run_concept (pick ONE by the recognition cue):\n" + run_lines + "\n"
        "  pass_concept (pick ONE by the recognition cue):\n" + pass_lines
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2) DETERMINISTIC RECOVERY — fill a null concept from what we already have
# ═══════════════════════════════════════════════════════════════════════════
def _mine_description(desc: str, lookup) -> Optional[str]:
    """Return the first concept whose alias appears in the coach description."""
    d = f" {(desc or '').lower()} "
    for name, _cue, aliases in lookup:
        for a in aliases:
            if a and a in d:
                return name
    return None


def infer_run_concept(play: Dict[str, Any]) -> Optional[Tuple[str, float, str]]:
    """(concept, confidence, source) for a run, or None. Description first (the
    model already wrote it), then structural signals."""
    hit = _mine_description(play.get("play_description"), _RUN_LOOKUP)
    if hit:
        return (hit, 0.75, "description")

    pt = (play.get("play_type") or "").lower()
    if "draw" in pt:
        return ("Draw", 0.6, "signals")
    if "option" in pt:
        return ("Speed Option", 0.55, "signals")
    if pt in ("qb run",) or "qb" in pt:
        return ("Zone Read", 0.5, "signals")

    # Structural: gap + direction. Interior = zone/dive; edge = outside/sweep.
    gap = (play.get("run_gap") or "").upper()
    direction = (play.get("run_direction") or "").lower()
    if "edge" in gap or gap.startswith("D") or gap == "C" or "outside" in direction:
        return ("Outside Zone", 0.45, "signals")
    if gap in ("A", "B") or "inside" in direction or "middle" in direction:
        return ("Inside Zone", 0.45, "signals")
    return None


def infer_pass_concept(play: Dict[str, Any]) -> Optional[Tuple[str, float, str]]:
    """(concept, confidence, source) for a pass, or None."""
    hit = _mine_description(play.get("play_description"), _PASS_LOOKUP)
    if hit:
        return (hit, 0.75, "description")

    # Screens are the most reliable structural read.
    if play.get("screen_subtype") or "screen" in (play.get("play_type") or "").lower():
        return ("Screen", 0.7, "signals")
    if play.get("is_play_action") is True:
        return ("PA Boot", 0.5, "signals")

    depth = (play.get("pass_depth") or "").lower()
    area = (play.get("target_area") or "").lower()
    if "deep" in depth and ("seam" in area or "middle" in area):
        return ("Four Verticals", 0.45, "signals")
    if ("behind" in depth or "short" in depth) and "flat" in area:
        return ("Quick Game", 0.4, "signals")
    return None


def _is_run(play: Dict[str, Any]) -> bool:
    rp = (play.get("run_pass") or "").lower()
    if rp == "run":
        return True
    if rp == "pass":
        return False
    pt = (play.get("play_type") or "").lower()
    return pt in ("run", "draw", "qb run", "option", "rush")


def _is_pass(play: Dict[str, Any]) -> bool:
    rp = (play.get("run_pass") or "").lower()
    if rp == "pass":
        return True
    if rp == "run":
        return False
    pt = (play.get("play_type") or "").lower()
    return pt in ("pass", "screen", "rpo", "play action", "play-action")


def fill_concepts(play: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure a run/pass play carries a concept. Mutates and returns the play dict.

    A concept the model already provided is KEPT (source 'model'). Otherwise it is
    recovered from the description, then structural signals. Records concept_source
    and concept_confidence for report honesty. Non-run/pass plays are untouched."""
    if _is_run(play):
        existing = (play.get("run_concept") or "").strip()
        if existing:
            play.setdefault("concept_source", "model")
            play.setdefault("concept_confidence", play.get("concept_confidence") or 0.85)
            return play
        got = infer_run_concept(play)
        if got:
            play["run_concept"], play["concept_confidence"], play["concept_source"] = got
    elif _is_pass(play):
        existing = (play.get("pass_concept") or "").strip()
        if existing:
            play.setdefault("concept_source", "model")
            play.setdefault("concept_confidence", play.get("concept_confidence") or 0.85)
            return play
        got = infer_pass_concept(play)
        if got:
            play["pass_concept"], play["concept_confidence"], play["concept_source"] = got
    return play
