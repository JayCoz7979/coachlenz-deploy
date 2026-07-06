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
from typing import Dict, Any, List, Optional

EXPORT_FORMATS = ("coordinator", "position", "head_coach", "player")

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
    spec = POSITION_UNITS.get(unit)
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
    else:
        raise ValueError(f"Unknown export format '{fmt}'. Valid: {', '.join(EXPORT_FORMATS)}")

    out["sport"] = report.get("sport")
    out["watermarked"] = bool(report.get("watermarked"))
    out["meta"] = _meta(report)
    out["generated_at"] = report.get("generated_at")
    return out
