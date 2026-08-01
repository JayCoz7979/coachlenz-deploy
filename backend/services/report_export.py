"""
Module 9 - the four report formats, as pure, testable functions.

A generated report holds `sections` (coach-facing prose) and `summary` (the raw
tendency data, including the football `scouting` block and `player_tendencies`).
This module reshapes that one report into the four audiences Module 9 specifies:

    coordinator   full detail - every section (the OC/DC report)
    position      filtered to one unit's matchups (WR/DB/OL/DL/QB/LB/RB/ST coach)
    head_coach    one page - top priorities per phase, coach-ready, no sample sizes
    player        one bulletin per identified player - plain-language matchup cue

Each format returns the SAME normalized shape ({title, subtitle, blocks:[{heading,
body}], ...}) so a single print/PDF renderer serves all four. No framework import
here - it stays unit-testable.
"""
import csv
import io
from typing import Dict, Any, List, Optional

from backend.services.plainify import plainify, pct_to_words
from backend.services import heatmap as _hm

EXPORT_FORMATS = ("coordinator", "position", "head_coach", "player", "player_onepager")

# The one FERPA line every player-facing page carries (§9 / §11).
CONFIDENTIAL_NOTE = ("This report is confidential. It contains performance data "
                     "covered under your institution's FERPA DPA with CoachLenz.")

# ── Play-level CSV export ────────────────────────────────────────────────────
# A flat, one-row-per-play sheet for coaches who want the tags in a spreadsheet.
# Columns are stable (this is a data contract other tools parse); test_report_export
# guards the schema.
CSV_COLUMNS = [
    "play_number", "down", "distance", "formation", "personnel", "play_type",
    "result", "concept", "blitz", "coverage", "jersey_numbers",
    "confidence_score", "timestamp",
]


def _blank(v: Any) -> Any:
    return "" if v is None else v


def _fmt_timestamp(seconds: Any) -> str:
    """Film position as m:ss (coach-readable). Blank when unknown."""
    if seconds is None:
        return ""
    try:
        s = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    return f"{s // 60}:{s % 60:02d}"


def _jersey_numbers(event: Any) -> str:
    """Semicolon-joined legible jerseys from extra_data.players, falling back to the
    play's primary actor (Event.player)."""
    extra = getattr(event, "extra_data", None) or {}
    nums = [str(p.get("jersey")) for p in (extra.get("players") or [])
            if isinstance(p, dict) and p.get("jersey")]
    if nums:
        return ";".join(nums)
    return str(getattr(event, "player", "") or "")


def plays_to_csv(events) -> str:
    """Flatten play Events into the CSV_COLUMNS schema. Pure: accepts any objects
    with the Event attributes (real rows or test stubs), returns the CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for i, e in enumerate(events, start=1):
        extra = getattr(e, "extra_data", None) or {}
        concept = extra.get("run_concept") or extra.get("pass_concept") or ""
        conf = extra.get("confidence")
        writer.writerow([
            i,
            _blank(getattr(e, "down", None)),
            _blank(getattr(e, "distance", None)),
            _blank(getattr(e, "formation", None)),
            _blank(getattr(e, "personnel", None)),
            _blank(getattr(e, "play_type", None)),
            _blank(getattr(e, "result", None)),
            concept,
            _blank(getattr(e, "blitz", None)),
            _blank(getattr(e, "coverage", None)),
            _jersey_numbers(e),
            "" if conf is None else round(float(conf), 3),
            _fmt_timestamp(getattr(e, "time_seconds", None)),
        ])
    return buf.getvalue()

# A position coach preparing OUR unit needs the OPPONENT tendencies that bear on
# that matchup. Map each unit to the section keywords that matter to it.
POSITION_UNITS: Dict[str, Dict[str, Any]] = {
    "OL": {"label": "Offensive Line",
           "keywords": ["front", "pressure", "blitz", "defense - fronts", "defensive"],
           "hint": "Their pass rush, blitz gaps, and stunts - where to slide protection."},
    "DL": {"label": "Defensive Line",
           "keywords": ["run game", "run", "gap", "protection"],
           "hint": "Their run concepts, gaps, and protection - where to win at the point of attack."},
    "WR": {"label": "Wide Receivers",
           "keywords": ["coverage", "secondary", "pass distribution"],
           "hint": "Their coverage leverage and technique - the routes that beat them."},
    "DB": {"label": "Defensive Backs",
           "keywords": ["pass game", "pass", "distribution", "motion"],
           "hint": "Their pass concepts, target areas, and top receivers - what you must take away."},
    "QB": {"label": "Quarterbacks",
           "keywords": ["coverage", "secondary", "fronts", "pressure", "blitz"],
           "hint": "Their coverage shells, disguise, and pressure - the pre-snap picture and answers."},
    "LB": {"label": "Linebackers",
           "keywords": ["run game", "run", "play action", "screen", "gap"],
           "hint": "Their run concepts, play-action, and screens - your run fits and pass drops."},
    "RB": {"label": "Running Backs",
           "keywords": ["front", "pressure", "blitz", "defensive"],
           "hint": "Their fronts and blitzes - protection assignments and check-down windows."},
    "ST": {"label": "Special Teams",
           "keywords": ["special teams", "kicking", "return", "fake"],
           "hint": "Their kicking game, return threat, and fake tendencies."},
}

# Basketball has no football-style position coaches; the practical unit split a staff
# thinks in is Guards / Wings / Bigs. Keywords map each to the basketball report
# sections that bear on that group (headings like "Ball Screen Defense", "Shot Chart",
# "Free Throws", "Systems, Press & Press-Break", "Key Players").
BASKETBALL_UNITS: Dict[str, Dict[str, Any]] = {
    "G": {"label": "Guards",
          "keywords": ["ball screen", "press", "defensive scheme", "situational", "late-game", "systems", "game plan"],
          "hint": "Their ball-screen actions, press and press-break, and defensive scheme - how your guards attack and defend on the ball."},
    "W": {"label": "Wings",
          "keywords": ["shot chart", "key players", "offensive system", "situational", "special situations"],
          "hint": "Their shot chart, key perimeter scorers, and offensive sets - what your wings take away and where to hunt shots."},
    "B": {"label": "Bigs",
          "keywords": ["shot chart", "ball screen", "free throw", "inbound", "key players", "installable game plan"],
          "hint": "Their paint scoring, ball-screen coverage, free-throw targets, and inbounds - your bigs' coverage and rebounding plan."},
}


def _units_for_sport(sport: Optional[str]) -> Dict[str, Dict[str, Any]]:
    return BASKETBALL_UNITS if (sport or "").strip().lower() == "basketball" else POSITION_UNITS


def _sections(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in (report.get("sections") or []) if isinstance(s, dict)]


def _match(section: Dict[str, Any], keywords: List[str]) -> bool:
    hay = (str(section.get("heading", "")) + " " + str(section.get("insight_type", ""))).lower()
    return any(k in hay for k in keywords)


def _meta(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    scouting = summary.get("scouting") or {} if isinstance(summary, dict) else {}
    return {
        "sport": report.get("sport"),
        "report_status": scouting.get("report_status"),
        "total_plays": (summary.get("total_plays") if isinstance(summary, dict) else None),
        "generated_at": report.get("generated_at"),
    }


# ── coordinator: the full report ─────────────────────────────────────────────
def _coordinator(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "coordinator",
        "title": report.get("title") or "Scouting Report",
        "subtitle": "Coordinator Report - full detail",
        "blocks": _sections(report),
    }


# ── position: one unit's slice ───────────────────────────────────────────────
def _position(report: Dict[str, Any], unit: Optional[str]) -> Dict[str, Any]:
    unit = (unit or "").upper()
    spec = _units_for_sport(report.get("sport")).get(unit)
    secs = _sections(report)
    if not spec:
        # Unknown unit: give the exploitable-pattern sections as a safe default.
        blocks = [s for s in secs if "exploitable" in str(s.get("heading", "")).lower()] or secs
        return {"format": "position", "title": report.get("title") or "Scouting Report",
                "subtitle": "Position Coach Brief", "unit": unit or None, "blocks": blocks}

    matched = [s for s in secs if _match(s, spec["keywords"])]
    # Always include the executive summary + any exploitable-pattern briefs for context.
    context = [s for s in secs if str(s.get("heading", "")).lower().startswith("executive")
               or "exploitable" in str(s.get("heading", "")).lower()]
    seen = set()
    blocks = []
    for s in context + matched:
        key = s.get("heading")
        if key not in seen:
            seen.add(key)
            blocks.append(s)
    if not blocks:
        blocks = secs  # never hand a coach an empty brief
    return {
        "format": "position",
        "title": report.get("title") or "Scouting Report",
        "subtitle": f"Position Coach Brief - {spec['label']}",
        "unit": unit,
        "unit_hint": spec["hint"],
        "blocks": blocks,
    }


# ── head coach: one page ─────────────────────────────────────────────────────
def _head_coach(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    scouting = (summary.get("scouting") or {}) if isinstance(summary, dict) else {}
    blocks: List[Dict[str, Any]] = []

    priorities = scouting.get("head_coach_priorities") or []
    if priorities:
        # Group the computed, ranked priorities by phase into a one-page tear sheet.
        by_phase = {"DEF": [], "OFF": [], "ST": []}
        for p in priorities:
            by_phase.setdefault(p.get("phase", "OFF"), []).append(p)
        phase_label = {"OFF": "Offense - Attack Their Defense",
                       "DEF": "Defense - Take This Away",
                       "ST": "Special Teams"}
        for phase in ("DEF", "OFF", "ST"):
            items = by_phase.get(phase) or []
            if items:
                body = "\n".join(f"- {it.get('call')} **[{it.get('confidence','')}]**" for it in items)
                blocks.append({"heading": phase_label[phase], "insight_type": "tendency", "body": body})

        # Featured explosive threats (Gate 6) get their own alert line.
        gates = scouting.get("validation_gates") or []
        alerts = next((g.get("alerts", []) for g in gates if g.get("gate") == 6), [])
        if alerts:
            body = "\n".join(f"- **{a.get('concept')}** ({a.get('area')}): {a.get('explosive_rate_pct')}% explosive"
                             for a in alerts[:4])
            blocks.insert(0, {"heading": "Explosive Threats - Featured", "insight_type": "tendency", "body": body})
    else:
        # Non-football or no scouting block: fall back to the summary + game-plan sections.
        secs = _sections(report)
        wanted = [s for s in secs if str(s.get("heading", "")).lower().startswith(("executive", "game plan",
                  "head coach", "situational")) or "priorit" in str(s.get("heading", "")).lower()]
        blocks = wanted or secs[:3]

    return {
        "format": "head_coach",
        "title": report.get("title") or "Scouting Report",
        "subtitle": "Head Coach Summary - one page",
        "blocks": blocks,
    }


# ── player bulletins ─────────────────────────────────────────────────────────
def _player_cue(p: Dict[str, Any]) -> str:
    """A plain-language, one-line 'what to expect / how to attack' from the stats."""
    cues = []
    expl = p.get("explosive_plays", 0)
    touches = p.get("touches", 0) or p.get("as_primary", 0)
    sr = p.get("success_rate", 0)
    if expl and touches and expl / max(touches, 1) >= 0.15:
        cues.append("big-play threat - do not let him get to the edge or behind you")
    if p.get("as_runner", 0) and p.get("as_runner", 0) >= p.get("as_passer_or_receiver", 0):
        cues.append("primary ball-carrier - set a hard edge and gang-tackle")
    elif p.get("as_passer_or_receiver", 0):
        cues.append("featured in the pass game - jam and reroute, know where he lines up")
    if sr and sr >= 55:
        cues.append(f"highly efficient ({sr}% success) - make someone else beat you")
    if p.get("fumble_risk"):
        cues.append("ball-security issues on film - punch at the ball")
    return "; ".join(cues) or "role player - stay disciplined in your assignment"


def _player(report: Dict[str, Any], player: Optional[str]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    pt = (summary.get("player_tendencies") or {}) if isinstance(summary, dict) else {}
    by_player = pt.get("by_player") or {}

    blocks: List[Dict[str, Any]] = []
    if not by_player:
        note = pt.get("note") or ("No legible jersey numbers were tracked on this film, so per-player "
                                  "bulletins are not available. Player tracking needs readable jerseys.")
        blocks.append({"heading": "Player Bulletins Unavailable", "insight_type": "tendency", "body": note})
        return {"format": "player", "title": report.get("title") or "Scouting Report",
                "subtitle": "Player Bulletins", "blocks": blocks}

    items = list(by_player.items())
    if player:
        want = str(player).lstrip("#")
        items = [(k, v) for k, v in items if str(v.get("jersey")) == want] or items[:1]

    for key, p in items:
        jersey = p.get("jersey", "?")
        team = p.get("team", "")
        role = next(iter(p.get("roles", {})), None)
        stat_bits = []
        if p.get("touches"):
            stat_bits.append(f"{p['touches']} touches, {p.get('avg_yards', 0)} avg, {p.get('success_rate', 0)}% success")
        if p.get("explosive_plays"):
            stat_bits.append(f"{p['explosive_plays']} explosive")
        top_play = next(iter(p.get("by_play_type", {})), None)
        if top_play:
            stat_bits.append(f"most-seen on {top_play}")
        body_lines = [f"- **On film:** {', '.join(stat_bits) or 'limited legible snaps'}"]
        if role:
            body_lines.append(f"- **Role:** {role}")
        body_lines.append(f"- **Your job:** {_player_cue(p)}")
        blocks.append({
            "heading": f"#{jersey}" + (f" ({team})" if team else "") + (f" - {role}" if role else ""),
            "insight_type": "tendency",
            "body": "\n".join(body_lines),
        })

    return {
        "format": "player",
        "title": report.get("title") or "Scouting Report",
        "subtitle": "Player Bulletins" + (f" - #{player}" if player else f" - {len(items)} players"),
        "blocks": blocks,
    }


# ── player one-pager (§11) ───────────────────────────────────────────────────
# The Player Layer: one print-ready page a 16-year-old reads once and knows what
# to do. THE KEY / WHO TO WATCH / WHAT THEY RUN / WHAT WE DO, all built from the
# structured summary and forced through plainify() so no percentage, jargon term,
# or long sentence can reach a player. This is a NEW format — the per-player
# `player` bulletins above are untouched.
_ZONE_LABELS = {
    "restricted area": "the paint", "paint non-ra": "the paint", "paint": "the paint",
    "corner 3": "the corner", "left corner 3": "the left corner", "right corner 3": "the right corner",
    "wing 3": "the wing", "top of key": "the top", "top of key 3": "the top",
    "mid-range": "the mid-range", "left mid-range": "the mid-range", "right mid-range": "the mid-range",
    "elbow": "the elbow",
}


def _zone_label(zone: Optional[str]) -> str:
    if not zone:
        return "there"
    return _ZONE_LABELS.get(str(zone).strip().lower(), str(zone).lower())


def _priorities(scouting: Dict[str, Any], sport: Optional[str]) -> List[Dict[str, Any]]:
    """The ranked directives, whichever sport's key holds them."""
    return (scouting.get("head_coach_priorities")
            or scouting.get("game_plan_priorities") or [])


def _priority_text(item: Dict[str, Any]) -> str:
    return str(item.get("call") or item.get("adjustment") or "").strip()


def _onepager_key(prios: List[Dict[str, Any]]) -> Optional[str]:
    """THE KEY — the single highest-value directive, in plain words."""
    if prios:
        k = plainify(_priority_text(prios[0]))
        if k:
            return k
    return None


def _bb_watch_cue(p: Dict[str, Any]) -> str:
    t = p.get("shot_tendency")
    if p.get("perimeter_dependency_flag") or t == "perimeter":
        return "Great shooter. Chase him off the line."
    if t == "paint_attacker":
        return "Drives hard. Wall off the paint."
    if t == "mid_range":
        return "Loves the mid-range. Contest every shot."
    if p.get("possession_role") == "initiator":
        return "Runs their offense. Pressure the ball."
    return "Stay in your stance. Do not gamble."


def _onepager_watch(summary: Dict[str, Any], sport: Optional[str]) -> List[Dict[str, str]]:
    """WHO TO WATCH — up to 3 jerseys, one plain phrase each."""
    pt = summary.get("player_tendencies") or {}
    by_player = pt.get("by_player") or {}
    out: List[Dict[str, str]] = []
    for _key, p in list(by_player.items())[:3]:
        jersey = str(p.get("jersey", "?"))
        if sport == "basketball":
            cue = _bb_watch_cue(p)
        else:
            # Football: the bulletins cue is already plain-ish; take its first clause.
            cue = (_player_cue(p).split(";")[0]).strip().capitalize()
        out.append({"jersey": jersey, "cue": plainify(cue)})
    return out


def _onepager_run(summary: Dict[str, Any], sport: Optional[str]) -> List[str]:
    """WHAT THEY RUN — up to 3 plain lines from structured tendencies."""
    lines: List[str] = []
    if sport == "basketball":
        so = summary.get("shooting_overview") or {}
        tp = so.get("three_point") or {}
        if (tp.get("pct_of_shots") or 0) >= 33:
            lines.append("They shoot lots of threes.")
        szm = summary.get("shot_zone_map") or {}
        if szm.get("most_frequent_zone"):
            lines.append(f"They love shots from {_zone_label(szm['most_frequent_zone'])}.")
        sc = summary.get("shot_creation") or {}
        best = sc.get("best_action") or sc.get("top_action")
        if best:
            lines.append(f"They score most in {str(best).lower()}.")
    else:
        off = summary.get("offense") or {}
        rp = off.get("run_pass_ratio") or {}
        run_pct = rp.get("run_pct")
        if run_pct is not None:
            if run_pct >= 55:
                lines.append(f"They run the ball {pct_to_words(run_pct)}.")
            elif run_pct <= 45:
                lines.append(f"They throw the ball {pct_to_words(100 - run_pct)}.")
            else:
                lines.append("They run and throw about the same.")
        tf = off.get("top_formations")
        if isinstance(tf, dict) and tf:
            lines.append(f"They line up most in {next(iter(tf))}.")
        tpl = off.get("top_plays")
        if isinstance(tpl, dict) and tpl:
            lines.append(f"Watch for their {str(next(iter(tpl))).lower()}.")
    return [plainify(l) for l in lines[:3]]


def _onepager_do(prios: List[Dict[str, Any]]) -> List[str]:
    """WHAT WE DO — up to 3 verb-first directives, in plain words."""
    out: List[str] = []
    for it in prios[:3]:
        line = plainify(_priority_text(it))
        if line:
            out.append(line)
    return out


# Player-layer 3-color palette (matches services.heatmap): red = worry, green = go.
_HEAT_RED = "#c0392b"
_HEAT_YELLOW = "#c9a227"
_HEAT_GREEN = "#1f7a3a"


def _onepager_football_heat(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Static 3-color 'where they run' strip for the football one-pager. Uses run
    direction (Left/Right/Inside/Outside) colored by volume — where they run most is
    red (load up), where they rarely go is green. Needs a real run sample; None when
    they're pass-heavy or the run map is thin (honest, no fabricated field)."""
    off = summary.get("offense") or {}
    rda = off.get("run_direction_analysis") or {}
    if (rda.get("total_runs") or 0) < 6:
        return None
    cells = []
    for label, key in (("Left", "left_pct"), ("Right", "right_pct"),
                       ("Inside", "inside_pct"), ("Outside", "outside_pct")):
        pct = rda.get(key)
        if pct is None:
            continue
        if pct >= 60:
            band, color = "red", _HEAT_RED
        elif pct >= 40:
            band, color = "yellow", _HEAT_YELLOW
        else:
            band, color = "green", _HEAT_GREEN
        cells.append({"zone": label, "band": band, "color": color, "label": ""})
    if not cells:
        return None
    return {"zones": cells, "caption": "Red = they run here most. Green = they rarely go here."}


def _onepager_heatmap(summary: Dict[str, Any], sport: Optional[str]) -> Optional[Dict[str, Any]]:
    """Static, print-safe 3-color heat strip for the one-pager: shot zones for
    basketball, run direction for football. None when the data is too thin, which
    keeps it honest."""
    if sport in ("football", "flag_football"):
        return _onepager_football_heat(summary)
    if sport != "basketball":
        return None
    szm = summary.get("shot_zone_map") or {}
    zones = szm.get("zones") or {}
    if not zones:
        return None
    ranked = sorted(zones.items(), key=lambda kv: -(kv[1].get("attempts") or 0))[:6]
    cells = []
    for zone, z in ranked:
        band = _hm.efg_band_player(z.get("efg_pct"), z.get("confidence"))
        cells.append({"zone": _zone_label(zone), "band": band["band"],
                      "color": band["color"], "label": band["label"]})
    return {"zones": cells, "caption": "Red = they score here. Green = make them shoot here."}


def _player_onepager(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    sport = (report.get("sport") or "").strip().lower()
    scouting = summary.get("scouting") or {}
    prios = _priorities(scouting, sport)

    key = _onepager_key(prios)
    watch = _onepager_watch(summary, sport)
    run = _onepager_run(summary, sport)
    do = _onepager_do(prios)
    if not key and watch:
        key = f"Stop #{watch[0]['jersey']}. Make someone else beat you."

    # A blocks view so any generic renderer still shows the content.
    blocks: List[Dict[str, Any]] = []
    if key:
        blocks.append({"heading": "THE KEY", "insight_type": "tendency", "body": key})
    if watch:
        blocks.append({"heading": "WHO TO WATCH", "insight_type": "tendency",
                       "body": "\n".join(f"- #{w['jersey']} {w['cue']}" for w in watch)})
    if run:
        blocks.append({"heading": "WHAT THEY RUN", "insight_type": "tendency",
                       "body": "\n".join(f"- {r}" for r in run)})
    if do:
        blocks.append({"heading": "WHAT WE DO", "insight_type": "red_zone",
                       "body": "\n".join(f"- {d}" for d in do)})

    return {
        "format": "player_onepager",
        "title": report.get("title") or "Scouting Report",
        "subtitle": "Player Game Plan",
        "key": key,
        "watch": watch,
        "run": run,
        "do": do,
        "heatmap": _onepager_heatmap(summary, sport),
        "confidential_note": CONFIDENTIAL_NOTE,
        "blocks": blocks,
    }


# ── public entry ─────────────────────────────────────────────────────────────
def build_export(report: Dict[str, Any], fmt: str,
                 unit: Optional[str] = None, player: Optional[str] = None) -> Dict[str, Any]:
    fmt = (fmt or "coordinator").lower()
    if fmt == "coordinator":
        out = _coordinator(report)
    elif fmt == "position":
        out = _position(report, unit)
    elif fmt == "head_coach":
        out = _head_coach(report)
    elif fmt == "player":
        out = _player(report, player)
    elif fmt == "player_onepager":
        out = _player_onepager(report)
    else:
        raise ValueError(f"Unknown export format '{fmt}'. Valid: {', '.join(EXPORT_FORMATS)}")

    out["sport"] = report.get("sport")
    out["watermarked"] = bool(report.get("watermarked"))
    out["meta"] = _meta(report)
    out["generated_at"] = report.get("generated_at")
    return out
