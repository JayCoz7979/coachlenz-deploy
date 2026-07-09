import json
import re
import anthropic
from typing import List, Dict, Any
from backend.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# Single source of truth: the report model comes from config (env-overridable),
# not a hardcode. Keeps config.ANTHROPIC_MODEL honest instead of drifting from it.
MODEL = settings.ANTHROPIC_MODEL


def _unescape(s: str) -> str:
    return (s.replace('\\n', '\n').replace('\\t', '\t')
             .replace('\\"', '"').replace('\\/', '/').replace('\\\\', '\\')).strip()


def _regex_extract_sections(text: str) -> List[Dict[str, Any]]:
    """Pull heading/insight_type/body out of a (possibly broken) JSON-ish array by
    splitting on each "heading" key. Tolerates unescaped quotes and raw newlines in
    the body that would break a real JSON parser."""
    out: List[Dict[str, Any]] = []
    for chunk in re.split(r'"heading"\s*:', text)[1:]:
        hm = re.match(r'\s*"(.*?)"', chunk, re.DOTALL)
        heading = _unescape(hm.group(1)) if hm else "Analysis"
        it = re.search(r'"insight_type"\s*:\s*"(.*?)"', chunk, re.DOTALL)
        insight = _unescape(it.group(1)) if it else "tendency"
        # Body: from "body": " to the LAST '"}' in this object's chunk (greedy).
        bm = re.search(r'"body"\s*:\s*"(.*)"\s*\}', chunk, re.DOTALL)
        if not bm:
            bm = re.search(r'"body"\s*:\s*"(.*)$', chunk, re.DOTALL)
        body = _unescape(bm.group(1)) if bm else ""
        if heading or body:
            out.append({"heading": heading or "Analysis", "insight_type": insight, "body": body})
    return out


def _parse_report_sections(raw: str) -> List[Dict[str, Any]]:
    """Turn the model's output into sections, tolerating malformed JSON. Tries real
    JSON (strict=False for literal newlines), then a regex extraction that survives
    unescaped quotes and other breakage from the model's own writing."""
    text = (raw or "").strip()
    # Strip a markdown fence if present.
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        text = (m.group(1) if m else text.split("```", 1)[-1]).strip()
        if text.startswith("json"):
            text = text[4:].strip()
    # Narrow to the JSON array if there's stray prose around it.
    if "[" in text and "]" in text:
        text = text[text.index("["): text.rindex("]") + 1]

    try:
        parsed = json.loads(text, strict=False)
        sections = [
            {"heading": s.get("heading", "Analysis"),
             "insight_type": s.get("insight_type", "tendency"),
             "body": s.get("body", "")}
            for s in parsed if isinstance(s, dict)
        ]
        if sections:
            return sections
    except Exception:
        pass

    sections = _regex_extract_sections(text)
    if sections:
        return sections

    return [{"heading": "Tendency Analysis", "insight_type": "tendency", "body": raw}]


def _total_plays(tendency_summary: Dict[str, Any]) -> int:
    try:
        return int(tendency_summary.get("total_plays", 0) or 0)
    except Exception:
        return 0


SYSTEM_PROMPT_FOOTBALL = """You are an elite football analyst writing an OPPONENT SCOUTING report for a head coach preparing for this week's game.

Your job: turn raw tendency data into specific, exploitable intelligence that gives the coaching staff a clear game plan.

RULES:
- Every stat you cite must come from the provided data — no invented numbers
- Always include play counts alongside percentages: "on 3rd & long (14 instances), they passed 86% of the time"
- Be direct. Coaches don't want hedging — tell them what the data says and what to do about it
- Offensive data = the OPPONENT on offense — advise how OUR DEFENSE should prepare
- Defensive data = the OPPONENT on defense — advise how OUR OFFENSE should attack
- Lead with the most exploitable finding in each section, not the most common one
- "Exploitable" means a tendency that is both strong (high %) AND has a counter-strategy

SECTION FORMATS (write for a coach scanning fast before a game, NOT an essay):
- Start each section with ONE short lead sentence, the single biggest takeaway.
- Then use BULLET POINTS (start each line with "- ") for the specifics: each tendency, each by-situation split, each exploitable pattern, and what to do about it. One idea per bullet, one sentence each.
- Bold the key numbers and calls with **double asterisks** so they pop when scanned, e.g. "- **86% pass** on 3rd & long (14 of 16), sit on the sticks."
- Every bullet includes counts, never "often" when you can say "7 of 9 times".
- Default to bullets. Only use a short paragraph for the one-line lead, never walls of text.
- Flag anomalies as their own bullet (e.g. a tendency that flips in the red zone).
"""


SYSTEM_PROMPT_BASKETBALL = """You are an elite basketball analyst writing an OPPONENT SCOUTING report for a head coach preparing for this week's game.

Your job: turn raw tendency and shot data into specific, exploitable intelligence the coaching staff can act on immediately.

RULES:
- Every stat you cite must come from the provided data — no invented numbers
- Always include attempt counts alongside percentages: "Pick and Roll (23 possessions, 54% FG)"
- Be direct. Coaches want intelligence, not hedging
- Offensive data = opponent on offense — advise how OUR DEFENSE should prepare
- Defensive data = opponent on defense — advise how OUR OFFENSE should attack them
- Lead with the most exploitable finding in each section
- "Exploitable" means a tendency that is both strong AND has a clear counter

SECTION FORMATS (write for a coach scanning fast before a game, NOT an essay):
- Start each section with ONE short lead sentence, the single biggest takeaway.
- Then use BULLET POINTS (start each line with "- ") for the specifics: each tendency, each hot/cold zone, each exploitable pattern, and what to do about it. One idea per bullet, one sentence each.
- Bold the key numbers with **double asterisks** so they pop when scanned, e.g. "- **54% FG** on the pick and roll (23 possessions), hedge hard."
- Every bullet includes counts, never "often" when you can say "14 of 19 possessions".
- Default to bullets. Only use a short paragraph for the one-line lead, never walls of text.
- Call out hot zones AND cold zones, each as its own bullet.
"""


async def generate_prose_sections(
    sport: str,
    tendency_summary: Dict[str, Any],
    report_type: str,
    is_trial: bool = False,
) -> List[Dict[str, Any]]:
    """Returns sections shaped as [{heading, body, insight_type}] for the report viewer."""

    if sport == "basketball":
        return await _generate_basketball_sections(tendency_summary, report_type, is_trial)

    plays = _total_plays(tendency_summary)

    if plays < 5:
        return [{
            "heading": "Not Enough Plays to Analyze Yet",
            "insight_type": "tendency",
            "body": (
                f"This report was generated from {plays} tagged play"
                f"{'s' if plays != 1 else ''}. Tendency analysis needs more plays to find "
                f"reliable patterns — ideally full game film (60+ plays), not a highlight reel.\n\n"
                f"To get a strong report: import full game film (every play, not just highlights), "
                f"let AI auto-detection tag the plays, then generate the report again."
            ),
        }]

    off_plays = int(tendency_summary.get("offense_plays", 0) or 0)
    def_plays = int(tendency_summary.get("defense_plays", 0) or 0)
    st_plays = int(tendency_summary.get("special_teams_plays", 0) or 0)
    scouting = tendency_summary.get("scouting") or {}

    # SELF-SCOUT: same facts, flipped voice — what YOU give away, what's working,
    # where you hurt yourself. Its own section set and prompt; opponent path untouched.
    if report_type == "self_scout":
        if (scouting.get("self_scout") or {}).get("available"):
            return await _generate_self_scout_sections(
                tendency_summary, scouting, plays, off_plays, def_plays, st_plays, is_trial)
        # Requested a self-scout but there's no offense to analyze — say so plainly
        # rather than silently handing back an opponent-framed report.
        return [{
            "heading": "Not Enough Offense to Self-Scout",
            "insight_type": "tendency",
            "body": (
                "A self-scout finds what YOUR offense is giving away, so it needs your offensive plays. "
                f"This film had {off_plays} offensive play{'s' if off_plays != 1 else ''} tagged, which isn't enough "
                "to read your own tendencies.\n\n"
                "Tag (or AI-detect) full offensive film, then generate the self-scout again. To break down an "
                "opponent instead, switch the report type back to Opponent."
            ),
        }]

    # Build sections based on available data
    sections_spec = [
        {
            "heading": "Executive Summary",
            "insight_type": "tendency",
            "instructions": (
                "2-3 paragraph overview of the opponent's identity. "
                "Lead with their offensive philosophy (run-first? spread? power?), then defensive identity, then special teams threat level. "
                "End with the single most important tendency the staff needs to know going into game week."
                + (
                    f" This report's validation status is {scouting.get('report_status', 'PRELIMINARY')} "
                    f"({scouting.get('total_plays', 0)} plays across {scouting.get('games_scouted', 1)} game(s)); "
                    "state it in one sentence and, if PRELIMINARY, note the sample is below the 60-play line so "
                    "reads should be verified on film before game-planning around them."
                    if scouting else ""
                )
            ),
        }
    ]

    # AUTO SCOUTING KEYS — the plain-English tendency layer, front and center.
    # This is the coach's #1 ask: "tell me the tendencies automatically." Every key
    # is pre-computed and ranked; the writer only states them.
    if scouting.get("scouting_keys"):
        sections_spec.append({
            "heading": "Auto Scouting Keys — What They Tip",
            "insight_type": "tendency",
            "instructions": (
                "THIS IS THE MOST IMPORTANT SECTION — put it right after the summary. "
                "Use scouting.scouting_keys, a pre-computed list ALREADY ranked most-exploitable first, each with "
                "a statement, sample, confidence (HIGH/MEDIUM/LOW), strength, exploit, and a featured flag. "
                "Present the keys VERBATIM as bullets in the given order. Format each: "
                "'- **[statement]** — [exploit] (N reps, CONFIDENCE)'. "
                "Lead with any featured:true keys (explosive/fake game-losers) — mark them 'GAME-LOSER:'. "
                "Do NOT invent, reorder, or merge keys, and do NOT drop the sample counts. "
                "An asterisk on a statement means a personnel/injury flag applied (Gate 7) — keep it and note it once. "
                "This is the tear-away tendency sheet a coach scans in 60 seconds."
            ),
        })

    # Checks & Balances (Module 7): surface the gate results up top so the staff
    # knows exactly how much to trust this report before reading tendencies.
    if scouting.get("validation_gates"):
        sections_spec.append({
            "heading": "Report Validation — Checks & Balances",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.validation_gates and scouting.report_status. This is a trust/integrity note. "
                "State the report_status (FINAL / PRELIMINARY) and why in one lead sentence. "
                "Then one bullet per gate that did NOT pass or that carries a caveat: cite the gate name and its note verbatim. "
                "If scouting.personnel_flagged is true, state plainly that affected tendencies dropped one confidence tier and carry an asterisk (Gate 7). "
                "If a gate surfaced Watch Items (Gate 3) or explosive TAKE-AWAY alerts (Gate 6), name them. "
                "Keep it tight — a coach needs to know in 20 seconds how hard to lean on this report."
            ),
        })

    if off_plays >= 5:
        sections_spec.append({
            "heading": "Opponent Offense — Run Game",
            "insight_type": "run",
            "instructions": (
                "Analyze their rushing attack with maximum depth. "
                "Use run_direction_analysis: inside vs outside split, left vs right directional preference, by-direction avg yards and success rate (cite counts for each). "
                "Use run_concept breakdown: what blocking schemes do they rely on (Zone, Power, Counter, etc.) and which work best. "
                "Which formations generate their best run plays? Hash tendencies. "
                "Short yardage and goal line approach — what direction and concept do they trust in critical short-yardage? "
                "Success rate and negative play rate on the ground. "
                "End with 2-3 specific, detailed defensive adjustments that attack their run tendencies directly."
            ),
        })
        sections_spec.append({
            "heading": "Opponent Offense — Pass Game",
            "insight_type": "pass",
            "instructions": (
                "Analyze their passing attack with maximum depth. "
                "Use pass_concept_analysis.by_concept: which concepts do they rely on, success rate per concept, explosive count per concept (cite all counts). "
                "Use pass_concept_analysis.by_depth: how do they distribute targets by depth (Behind LOS vs Short vs Intermediate vs Deep) — what works, what doesn't? "
                "Motion analysis: do they use motion to signal pass concepts? Avg yards with vs without motion. "
                "3rd down pass tendencies by distance bucket. "
                "Which formations feed the pass game? "
                "Explosive pass play rate and the specific concepts that create them. "
                "End with 2-3 specific coverage/pressure adjustments that attack their pass tendencies."
            ),
        })
        sections_spec.append({
            "heading": "Opponent Offense — Pass Distribution & Motion",
            "insight_type": "pass",
            "instructions": (
                "Use pass_distribution: where do they throw the ball on the field? "
                "Cite by_area detail (count, pct_of_passes, avg_yards, success_rate per zone). "
                "Name the hottest area and most effective area. "
                "Use field_side_distribution: left vs middle vs right — do they have a field preference? "
                "Use motion_type_analysis.by_type: which motion type leads to which play concept and how often? "
                "Does Jet Motion signal sweep? Does H-Back Motion signal power run? Cite the top_concepts per motion type. "
                "If they use tempo (no_huddle_hurry_pct > 10%), describe when and how effectively. "
                "Advise: which coverage leverages cut off their best target area? Which LB must spy jet motion?"
            ),
        })
        sections_spec.append({
            "heading": "Opponent Offense — Situational",
            "insight_type": "red_zone",
            "instructions": (
                "Cover their tendencies in critical situations: "
                "Red zone (what do they like inside the 20? Success rate? Scoring rate?), "
                "3rd down (by distance bucket — long/medium/short — cite specific plays and counts), "
                "short yardage (3rd & 1-3, 4th & short — what do they call, do they convert?), "
                "drive-opening tendencies (first play tendencies if data shows a pattern). "
                "Call out any situational tendencies that are especially exploitable."
            ),
        })
        sections_spec.append({
            "heading": "EXPLOITABLE OFFENSIVE PATTERNS",
            "insight_type": "tendency",
            "instructions": (
                "This section is a bullet-point intelligence brief for the defensive coordinator. "
                "List 4-6 specific, exploitable tendencies with the counter for each. Format each bullet as:\n"
                "• [TENDENCY]: [what they do and how often] → [COUNTER]: [specific adjustment]\n"
                "Examples of the depth expected:\n"
                "• SHOTGUN RUN: 73% run rate from Shotgun (22/30 instances), avg 6.2 yds — they disguise it as pass → Load box with a nickel/safety blitz when they align in Shotgun on 1st down\n"
                "• 3RD & LONG: 89% pass, primarily screens and quick game (11/17 instances) → Press corners, linebacker spy to contain screen game\n"
                "Only include tendencies with enough sample size to be reliable (5+ instances minimum). "
                "This is the most important section in the report."
            ),
        })

    if def_plays >= 5:
        sections_spec.append({
            "heading": "Opponent Defense — Fronts & Pressure",
            "insight_type": "defense",
            "instructions": (
                "Analyze their defensive front and pressure package with maximum depth. "
                "Use pressure_gap_analysis: WHERE does their blitz come from (edge left/right, A-gap, interior)? Which gap produces sacks vs. which gives up explosives? "
                "Use defensive_shell_analysis.pressure_types: 4-man vs 5-man vs 6-man+ distribution and effectiveness (cite counts, avg yards allowed, sacks per type). "
                "Front/coverage pairings — what do they pair most often? "
                "Blitz by situation (cite each bucket from blitz_by_situation). "
                "Use pressure_results: does their blitz actually work or does it give up big plays? "
                "Advise OL: where should protection slide? Which blitz gaps need a hot route answer?"
            ),
        })
        sections_spec.append({
            "heading": "Opponent Defense — Coverage & Secondary",
            "insight_type": "defense",
            "instructions": (
                "Analyze their secondary with maximum depth. "
                "Use safety_disguise_analysis.shell_to_rotation_map: what do safeties actually do post-snap vs. their pre-snap shell? If disguise_rate > 30%, say so explicitly — this team disguises. If < 15%, they tip. "
                "Use safety_disguise_analysis.corner_techniques: are corners in press, off/cushion, or bail? This tells which routes attack them. "
                "Use defensive_shell_analysis.coverage_shells and shell_to_coverage_map: the full pre-snap → post-snap picture. "
                "Coverage by down bucket. Coverage vs. formations faced. Red zone coverage. "
                "Advise OC specifically: which pass concepts, route combinations, and personnel groups beat what they show? "
                "If they press, attack with slants and fades. If they bail, attack with quick game and screens. Say it that specifically."
            ),
        })
        sections_spec.append({
            "heading": "EXPLOITABLE DEFENSIVE PATTERNS",
            "insight_type": "tendency",
            "instructions": (
                "Bullet-point intelligence brief for the offensive coordinator. "
                "List 4-6 specific, exploitable defensive tendencies with the attack for each. Format:\n"
                "• [TENDENCY]: [what they do and how often] → [ATTACK]: [specific play call / concept / formation]\n"
                "Only include tendencies with enough sample size. This is critical game-planning intelligence."
            ),
        })

    if st_plays >= 3:
        sections_spec.append({
            "heading": "Opponent Special Teams — Kicking Game",
            "insight_type": "special_teams",
            "instructions": (
                "Use the special_teams data block in full. This must be coaching-grade, not a summary. "
                "FIELD GOALS: cite field_goals.by_range — make percentage at each range (inside_30, 30_39, 40_49, 50_plus), "
                "their realistic make range, long_made, and blocked count. State the exact distance beyond which they become unreliable "
                "(that is the line where you take points off the board / go for it on 4th down). "
                "PUNTS: avg_gross_yards, longest, inside_20 pct (do they pin deep?), touchback pct, fair_catches_forced, "
                "shanks_under_35 (operation reliability), directional_pct (do they punt to a side you can set up a return on?), "
                "and coverage_allowed (avg_return_allowed, explosive_allowed, td_allowed). "
                "KICKOFFS: touchback pct (do you even get a return chance?), onside_attempts/recovered, directional_pct, coverage_allowed. "
                "PAT/2PT: pat make rate and two_point_rate (are they aggressive?). "
                "Advise: FG block opportunities (long attempts, blocked history), where to attack their coverage, "
                "and operation weaknesses (shanks, bad snaps via snap_issues, blocks allowed)."
            ),
        })
        sections_spec.append({
            "heading": "Opponent Special Teams — Return Game & Fakes",
            "insight_type": "special_teams",
            "instructions": (
                "Use punt_returns, kick_returns, return_game_overall, fakes_and_trick, and block_unit. "
                "RETURN THREAT: punt and kick return avg, longest, touchdowns, explosive_25plus, fair_catch rate, muffs_fumbles "
                "(ball security you can attack), and by_scheme (which return scheme they favor — middle, wall left/right, reverse). "
                "Tell the coverage units exactly where the return is coming and how dangerous the returner is. "
                "FAKE ALERT: fakes_and_trick count, success_rate, and the situations (down/distance/field_position) where they fake — "
                "name the exact down-and-distance and field zones to stay alert. "
                "BLOCK THREAT: block_unit (do they rush kicks aggressively, have they blocked kicks?). "
                "Advise: returner containment plan, fake-alert situations, and whether to protect against a block rush."
            ),
        })

    if off_plays >= 5:
        sections_spec.append({
            "heading": "Opponent Offense — Game Script Tendencies",
            "insight_type": "tendency",
            "instructions": (
                "Use score_situation_analysis: do their tendencies shift based on score? "
                "Compare run/pass split and avg yards when Leading vs Trailing vs Tied. "
                "If they abandon the run when trailing, say it explicitly — that tells the defense when to go to pass-rush mode. "
                "If they run MORE when leading, that tells us to force them into third-and-long situations. "
                "Only include this section if score_situation_analysis has data for 2+ situations. "
                "Keep this section tight — 1-2 paragraphs focused on the most actionable game-script intelligence."
            ),
        })
    if scouting.get("game_plan"):
        # Module 8: present the ALREADY-computed, evidence-backed game plan. Each
        # item carries a sample size and confidence tier; recommendations (10+ reps)
        # outrank watch items (Gate 3). The writer turns real numbers into calls.
        sections_spec.append({
            "heading": "Situational Tendency Report",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.situational_tendencies — a pre-computed list of coordinator statements, each with a "
                "sample size and confidence tier (HIGH/MEDIUM/LOW). Present them VERBATIM as bullets, HIGH confidence first. "
                "Each bullet is one statement followed by its (sample, confidence). Do not invent numbers. "
                "An asterisk on a statement means a personnel/injury flag applied (Gate 7) — keep the asterisk and note it once."
            ),
        })
        sections_spec.append({
            "heading": "Coordinator Game Plan — Installable Calls",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.game_plan (defensive_plan, offensive_plan, special_teams_plan) — ALREADY computed and ranked. "
                "Present three short subsections (DEFENSE, OFFENSE, SPECIAL TEAMS). Under each, bullet the items in the given order: "
                "'- [call] — [evidence] (sample N, CONFIDENCE)'. Present recommendations first, then watch items labeled '(WATCH ITEM — thin sample)'. "
                "Do NOT reorder within a phase and do NOT invent items. Every call already ties to a real number in its evidence field. "
                "This is the tear-away install sheet: a coordinator should be able to install it Tuesday and call it Friday."
            ),
        })
        sections_spec.append({
            "heading": "Head Coach Summary — Top Priorities",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.head_coach_priorities — the flat, priority-ordered digest across all phases. "
                "Present as a numbered list VERBATIM in the given order: '1. [PHASE]: [call] (CONFIDENCE)'. "
                "One page, coach-ready language, no sample sizes on this list — just the call and the confidence rating. "
                "This is the head coach's one-pager."
            ),
        })
    else:
        sections_spec.append({
            "heading": "Game Plan Priorities",
            "insight_type": "red_zone",
            "instructions": (
                "Numbered priority list — the 5-7 most important game-plan items across offense, defense, and special teams. "
                "Each item should be specific and actionable, not generic. "
                "Number them in priority order. "
                "Format: 1. [PHASE — O/D/ST]: [specific game plan item tied to a specific tendency from the data]"
            ),
        })

    sections_spec.append({
        "heading": "Scout's Note: Single-Camera Coverage & Confidence",
        "insight_type": "tendency",
        "instructions": (
            "Use the data_confidence block. This is a transparency note, not a sales pitch — coaches trust honesty. "
            "State the overall confidence_band (high / medium / low) and avg_confidence, and what it means for how to use this report. "
            "If low_confidence_pct is meaningful, say plainly that those reads should be verified on film before game-planning around them. "
            "List the top_blind_spots verbatim (the limitation phrases) so the coach knows exactly what the fixed single-camera angle could NOT see "
            "(e.g. backside blocking, coverage rotation behind the line, far-hash action cut off). "
            "If blind_spot_count is 0 and confidence is high, say so in one sentence. "
            "Never overstate certainty. The goal is that a coach knows precisely how much to lean on each finding."
        ),
    })

    # Build the prompt
    section_outline = "\n".join(
        f"{i+1}. \"{s['heading']}\" (insight_type: \"{s['insight_type']}\")\n   Instructions: {s['instructions']}"
        for i, s in enumerate(sections_spec)
    )

    prompt = f"""Sport: {sport}
Report Type: {report_type}
Sample Size: {plays} total plays (opponent offense: {off_plays}, opponent defense: {def_plays}, special teams: {st_plays})

TENDENCY DATA:
{json.dumps(tendency_summary, indent=2)}

Write a complete opponent scouting report as a JSON array. Each element: {{"heading": "...", "insight_type": "...", "body": "..."}}.

SECTIONS (write every one, in this exact order):
{section_outline}

BODY FORMAT (a coach scans this fast, do NOT write essays):
- Each section body = ONE short lead sentence, then a blank line, then BULLET POINTS. Put each bullet on its own line starting with "- ".
- One tendency or one action per bullet, one sentence each.
- Bold key numbers and calls with **double asterisks** so they pop, e.g. "- **86% pass** on 3rd & long (14 of 16), sit on the sticks."
- Every bullet cites play counts alongside percentages.
- Lead each section (the one sentence) with the most exploitable finding.
- Separate the lead sentence from the bullets with a blank line (\\n\\n) so they format as a list.
- Do not write multi-sentence paragraphs. Default to bullets everywhere.

Return ONLY the JSON array, nothing else."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        system=SYSTEM_PROMPT_FOOTBALL,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    sections = _parse_report_sections(raw)

    if is_trial:
        sections.append({
            "heading": "Trial Report",
            "insight_type": "tendency",
            "body": "This is a trial report. Upgrade at coachlenz.com to unlock full reports and exports.",
        })
    return sections


async def _generate_self_scout_sections(tendency_summary, scouting, plays,
                                        off_plays, def_plays, st_plays, is_trial):
    """Self-scout report: 'what am I giving away before someone else finds it?'
    Built from scouting.self_scout (predictability / winning concepts / self-inflicted),
    the same analytics as the opponent report, turned inward."""
    sections_spec = [
        {
            "heading": "Self-Scout Summary",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.self_scout.summary and scouting.self_scout.biggest_giveaway. "
                "2-3 sentences: what is this offense's identity, and the single biggest thing you are tipping. "
                "Frame it as a coach self-scouting before Friday — honest, direct, fix-it tone."
            ),
        },
        {
            "heading": "What You're Giving Away — Predictability",
            "insight_type": "tendency",
            "instructions": (
                "THE MOST IMPORTANT SECTION. Use scouting.self_scout.predictability, ALREADY ranked loudest-tip first. "
                "Each item: statement, sample, confidence, fix. Present VERBATIM as bullets, strongest first. "
                "Format: '- **[statement]** — Fix: [fix] (N reps, CONFIDENCE)'. "
                "These are the tells an opponent's film crew will find. Do not invent or reorder."
            ),
        },
        {
            "heading": "What's Working — Keep Feeding It",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.self_scout.winning_concepts (ranked by success rate). Each: statement, sample, success_rate. "
                "Present VERBATIM as bullets. Format: '- **[statement]**'. "
                "These are your money plays — the point is to keep calling what wins. If the list is empty, say the sample "
                "is too thin to confirm winners yet and move on."
            ),
        },
        {
            "heading": "Where You're Hurting Yourself",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.self_scout.self_inflicted (negative plays, penalties, turnovers). Each: statement, count. "
                "Present as bullets, biggest count first. Format: '- **[statement]**'. "
                "If the list is empty, say the offense is clean in this sample. Blunt, corrective tone."
            ),
        },
        {
            "heading": "Scout's Note: Single-Camera Coverage & Confidence",
            "insight_type": "tendency",
            "instructions": (
                "Use the data_confidence block. State the confidence_band and avg_confidence and what it means. "
                "List top_blind_spots verbatim so the coach knows what the fixed angle could not read. Never overstate certainty."
            ),
        },
    ]

    section_outline = "\n".join(
        f"{i+1}. \"{s['heading']}\" (insight_type: \"{s['insight_type']}\")\n   Instructions: {s['instructions']}"
        for i, s in enumerate(sections_spec)
    )

    prompt = f"""Sport: football
Report Type: self_scout
Sample Size: {plays} total plays (your offense: {off_plays}, your defense: {def_plays}, special teams: {st_plays})

TENDENCY DATA:
{json.dumps(tendency_summary, indent=2)}

Write a complete SELF-SCOUT report as a JSON array. This is the coach's own team looking in the mirror:
find what they are giving away before an opponent does. Each element: {{"heading": "...", "insight_type": "...", "body": "..."}}.

SECTIONS (write every one, in this exact order):
{section_outline}

BODY FORMAT (a coach scans this fast, do NOT write essays):
- Each section body = ONE short lead sentence, then a blank line, then BULLET POINTS on their own lines starting with "- ".
- One point per bullet, one sentence each. Bold key numbers and calls with **double asterisks**.
- Every bullet cites play counts alongside percentages. Lead each section with the most important finding.
- Do not write multi-sentence paragraphs. Default to bullets everywhere.

Return ONLY the JSON array, nothing else."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        system=SYSTEM_PROMPT_FOOTBALL,
        messages=[{"role": "user", "content": prompt}],
    )
    sections = _parse_report_sections(message.content[0].text.strip())
    if is_trial:
        sections.append({
            "heading": "Trial Report",
            "insight_type": "tendency",
            "body": "This is a trial report. Upgrade at coachlenz.com to unlock full reports and exports.",
        })
    return sections


def _scout_priority_sections(scouting):
    """The six scouting categories in STRICT priority order (Category 1 heaviest),
    then the auto-generated Game Plan Priorities. Each section is fed by the
    already-computed tendency_summary["scouting"] block, so the writer only has to
    turn real numbers into coach language."""
    return [
        {
            "heading": "Executive Summary",
            "insight_type": "tendency",
            "instructions": (
                "3-4 tight sentences on this opponent's identity across the six scouting categories. "
                "Lead with Category 1: name the primary_ball_handler and their possession_share_pct, and if "
                "isolation_dependency_flag is true say plainly they are isolation-dependent (>35% of possession in one player). "
                "Then one line each on their biggest turnover risk, their shot-selection lean (2PT vs 3PT), and their pace_rating. "
                "End with the single most important thing the staff must know, drawn from game_plan_priorities[0]."
            ),
        },
        {
            "heading": "Section 1 - Possession Control (Player Time of Possession)",
            "insight_type": "tendency",
            "instructions": (
                "THE HIGHEST-PRIORITY SECTION. Use scouting.category_1_time_of_possession. "
                "Open with one lead sentence naming the primary_ball_handler, their possession_share_pct and role. "
                "Then bullets: rank the top players by possession_seconds with their role (initiator / role_player / ghost), "
                "possession_share_pct, touches, and avg_seconds_per_touch. "
                "If isolation_dependency_flag is true, make it the headline bullet: one player over the 35% possession line is an "
                "isolation dependency to attack by denying/trapping that player. "
                "Name secondary_initiators (who else creates), ghost_players (players who never really handle it), and "
                "dead_zone_players (catch-and-immediately-pass, avg under 1s/touch). "
                "Close with the defensive call: who to deny/trap on the catch, and who to sag off."
            ),
        },
        {
            "heading": "Section 2 - Turnover Profile",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.category_2_turnovers. Lead with the team_rate_per_possession and team_rate_per_10_min. "
                "Bullets, ranked most dangerous to least: by_type (which turnover types they commit), by_situation "
                "(half-court / transition / press / late-game), and the per-player list with counts. "
                "Flag any player with a pattern_flags entry (2+ turnovers of the SAME type) as a repeatable weakness. "
                "Note most_dangerous_defender and generated_by_defender if present (which of their defenders forces turnovers, "
                "so OUR offense can avoid them). Close with which players to pressure and in which situation."
            ),
        },
        {
            "heading": "Section 3 - Deflection Vulnerability",
            "insight_type": "defense",
            "instructions": (
                "Use scouting.category_3_deflections. Lead with neutralize_first_defender (their best deflection defender). "
                "Bullets: per-defender deflections with conversion_pct (how often a deflection flips possession), "
                "the passing_lane_vulnerability chart and most_vulnerable_lane (which lane they attack passes in). "
                "Advise OUR offense: attack away from their best deflector and stop feeding the most_vulnerable_lane. "
                "If total is 0, say deflection data was not tagged for this game and skip the rest."
            ),
        },
        {
            "heading": "Section 4 - Shot Selection Tendencies (2PT vs 3PT)",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.category_4_shot_ratio. Lead with the overall 2PT vs 3PT split: attempts_2pt, attempts_3pt, "
                "three_pt_rate_pct, and ratio_2pt_to_3pt. "
                "Bullets: by_half (first vs second), by_possession_origin (pnr / transition / set / broken), and the "
                "fourth_quarter / when_trailing behavior with late_game_shift (do they go small and jack threes, or attack the paint?). "
                "Flag every player in perimeter_dependent_players (3PA over 40% of their shots) and give each player's tendency "
                "(paint_attacker / mid_range / perimeter / balanced). Close with what shot to take away."
            ),
        },
        {
            "heading": "Section 5 - Pace Profile",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.category_5_pace. Lead with pace_rating (slow/moderate/fast) and the avg_offensive_possession_seconds. "
                "Bullets: avg offensive vs defensive possession seconds, transition_frequency_pct (share of possessions starting "
                "within 5 seconds of a change), situational_pace (do they speed up or slow down when trailing vs leading), and "
                "pace_control (coach_controlled = consistent, player_driven = variable). "
                "Close with the tempo plan: speed them up or slow them down, and when. "
                "If tracked is false, say possession-timing was not tagged and skip."
            ),
        },
        {
            "heading": "Section 6 - Scoring Zone Map",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.category_6_scoring_areas. Lead with team_efg_pct and the single top scoring zone. "
                "Bullets: top_scoring_zones (comfort zones - high attempt AND high eFG%) each with eFG% and attempts, then "
                "avoid_zones (low eFG%). "
                "Put defensive_priority_zones in their OWN bullet flagged as MUST TAKE AWAY - these are zones over 55% eFG. "
                "Name the per-player eFG leaders from players[]. Close with the exact zones our defense funnels them away from."
            ),
        },
        {
            "heading": "Game Plan Priorities - Top Defensive Adjustments",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.game_plan_priorities, which is ALREADY ranked (Category 1 weighted heaviest). "
                "Present those items VERBATIM as a numbered list in the given order - do not reorder or drop them. "
                "Format each: '1. [CATEGORY]: [adjustment]'. "
                "After the computed items, you may add up to 2 more supporting adjustments ONLY if clearly backed by the data. "
                "This is the coach's tear-away sheet: specific, actionable, tied to a real number in every line."
            ),
        },
    ]


def _bball_sections(scouting, tendency_summary):
    """Assemble the basketball report: six priority sections + game plan, then any
    film-depth sections whose data actually exists, then the Scout's Note. Keeps a
    manual box-score report clean while a full-film report keeps its depth."""
    spec = _scout_priority_sections(scouting)

    # ── Coordinator layer (Modules 8-12): only when the coordinator data exists,
    # so a thin manual box-score report doesn't sprout empty sections. These are
    # inserted right after the six priority sections — they ARE the game prep. ──
    if scouting.get("validation_gates"):
        spec.append({
            "heading": "Report Integrity - Eight Validation Gates",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.report_status, scouting.validation_gates (eight gates), scouting.personnel_flagged, and "
                "scouting.camera_confidence. Open with the report_status (FINAL or PRELIMINARY) and total_possessions across "
                "games_scouted. Then one tight bullet per gate: name, passed (true/false), and the first note. "
                "If personnel_flagged is true, state plainly that affected tendencies dropped one confidence tier and carry an "
                "asterisk (Gate 8). Fold in camera_confidence.disclosure verbatim as the integrity note. This is a trust/integrity "
                "section, not a sales pitch - the coach must know exactly how hard to lean on this report."
            ),
        })
    if scouting.get("situational_tendencies"):
        spec.append({
            "heading": "Situational Tendencies - Coordinator Statements",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.situational_tendencies - a pre-computed list of coordinator statements, each already carrying its "
                "sample size and a confidence tier (HIGH / MEDIUM / LOW). Present them as a bulleted list in the given order, each "
                "line ending with its confidence and sample, e.g. '... [HIGH, n=25]'. Do not invent numbers - every statement is "
                "already evidence-backed. A trailing asterisk means the tendency was drawn from a game with a missing starter."
            ),
        })
    _gp = scouting.get("game_plan") or {}
    if any(_gp.get(k) for k in ("defensive_plan", "offensive_plan", "special_situations_plan")):
        spec.append({
            "heading": "Installable Game Plan - Offense / Defense / Special Situations",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.game_plan (defensive_plan, offensive_plan, special_situations_plan) - ALREADY computed and ranked. "
                "Present three labeled subsections. Within each, list items in order; featured items lead. Format each call: "
                "'CALL - evidence [CONFIDENCE, n=SAMPLE]'. Mark items whose class is 'watch_item' as (watch item) - they are below "
                "the 10-rep recommendation line and must NOT be presented as hard recommendations. The defensive_plan is the meat "
                "(how we guard THEIR offense); include the late-game denial, strategic foul target, and never-foul players if present."
            ),
        })
    lg = scouting.get("late_game_profile") or {}
    if lg.get("tracked"):
        spec.append({
            "heading": "Late-Game Profile - Final Four Minutes, One Possession",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.late_game_profile. Lead with primary_threat if primary_threat_alert is true - the player who takes "
                "over 40% of shots in the final four minutes of a one-possession game gets a dedicated defensive assignment. Bullets: "
                "late_shots, late_fg_pct, late_three_rate_pct, late_turnovers, and the shot_takers list with share_pct. Close with the "
                "final-four-minute defensive call. This is the single highest-priority read for a head coach."
            ),
        })
    ft = scouting.get("free_throw_profile") or {}
    if ft.get("tracked"):
        spec.append({
            "heading": "Free Throws - Strategic Foul Targets & Box-Outs",
            "insight_type": "defense",
            "instructions": (
                "Use scouting.free_throw_profile. Lead with team_ft_pct. Put strategic_foul_targets in their OWN bullet flagged "
                "FOUL LATE (players under 60% with a real sample) and never_foul_players flagged DO NOT FOUL LATE (over 90%). "
                "List per-player ft_pct and clutch_ft_pct where present, and note shooter_tempo for strategic foul timing. "
                "Summarize offensive_boxout_formations and defensive_boxout_formations if logged."
            ),
        })
    ss = scouting.get("special_situations") or {}
    if ss.get("tracked"):
        spec.append({
            "heading": "Special Situations - Trusted Sets (BLOB / SLOB / Press / Late)",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.special_situations.by_type. For each situation type present (BLOB, SLOB, press_break, last_second, "
                "end_of_quarter), name the trusted sets (reps >= 2) with their formation/action, reps, and scores. Flag every entry "
                "in trusted_late_sets as a MUST-DEFEND - a set they run more than once late and close is their most trusted call. "
                "Advise the exact coverage for each."
            ),
        })
    cst = scouting.get("coach_scheme_tags") or {}
    if cst.get("tracked"):
        spec.append({
            "heading": "Systems, Press & Press-Break (coach-tagged)",
            "insight_type": "tendency",
            "instructions": (
                "Use scouting.coach_scheme_tags - the offense/defense systems, presses, and press-breaks the coach tagged "
                "while charting film. Lead with primary_offense and primary_defense. Bullets: offensive_sets (most-run sets "
                "with counts), defensive_schemes (what they play and how often), presses (each press type WITH its "
                "time_markers - e.g. 'Full-court man press, first seen 6:12, 4 times'), and press_breaks (what beat a press, "
                "with time_markers). Any unorthodox/custom entry is the COACH'S OWN WORDS for a special call - surface it "
                "VERBATIM so it makes the report. If a press shows time markers, tell our staff to be ready for it at those "
                "points in the game."
            ),
        })
    if scouting.get("head_coach_priorities"):
        spec.append({
            "heading": "Head Coach One-Sheet - Top Priorities",
            "insight_type": "red_zone",
            "instructions": (
                "Use scouting.head_coach_priorities - the flat, priority-ordered digest across offense, defense, and special "
                "situations. Present VERBATIM as a numbered list in the given order: 'N. [PHASE] call (CONFIDENCE)'. Do not reorder "
                "or drop items. This is the tear-away sheet the head coach carries onto the floor."
            ),
        })

    def has(block, key="total", minv=0):
        b = tendency_summary.get(block) or {}
        try:
            return int(b.get(key, 0) or 0) > minv
        except Exception:
            return False

    # Film-depth candidates: (condition, section). Only emitted when data present.
    if has("pick_and_roll", "total_pnr") or has("isolation", "total_iso") or has("transition", "total"):
        spec.append({
            "heading": "Film Depth - Offensive System",
            "insight_type": "tendency",
            "instructions": (
                "Only from real data. Use pick_and_roll (roll vs pop, preferred_position, fg_pct), isolation, post_up, and "
                "transition to describe their primary half-court and early-offense actions. Cite counts and FG%. "
                "Advise the scheme that stops their main action."
            ),
        })
    if has("inbound_plays"):
        spec.append({
            "heading": "Film Depth - Inbound Plays (BLOB / SLOB)",
            "insight_type": "tendency",
            "instructions": (
                "Only if inbound_plays.total > 0. Use inbound_plays.blob and .slob: most_used_set, best_set, primary action, "
                "hottest_zone, after-timeout tendencies. Advise exactly how to take away their best BLOB and SLOB."
            ),
        })
    if has("ball_screen_defense"):
        spec.append({
            "heading": "Film Depth - Ball Screen Defense Attack Plan",
            "insight_type": "defense",
            "instructions": (
                "Only if ball_screen_defense.total > 0. Use primary_hedge and hedge_distribution to say how THEY guard ball "
                "screens (Drop / Switch / Hedge / ICE / Blitz) and what each leaves open for OUR offense to attack."
            ),
        })
    if has("defensive_scheme"):
        spec.append({
            "heading": "Film Depth - Defensive Scheme",
            "insight_type": "defense",
            "instructions": (
                "Only if defensive_scheme.total > 0. Use primary_scheme, man_pct, zone_pct, press_count and by_scheme "
                "(quarters_used) to describe their base defense and any changeups. Advise how to break the primary scheme."
            ),
        })

    spec.append({
        "heading": "Scout's Note - Single-Camera Coverage & Confidence",
        "insight_type": "tendency",
        "instructions": (
            "Use the data_confidence block (UATP transparency, not a sales pitch). State confidence_band (high/medium/low) and "
            "avg_confidence and what it means for how hard to lean on this report. If low_confidence_pct is meaningful, say those "
            "reads should be verified on film first. List top_blind_spots verbatim so the coach knows what the fixed single-camera "
            "angle could NOT see. If blind_spot_count is 0 and confidence is high, say so in one sentence. Never overstate certainty."
        ),
    })
    return spec


async def _generate_basketball_sections(
    tendency_summary: Dict[str, Any],
    report_type: str,
    is_trial: bool = False,
) -> List[Dict[str, Any]]:
    """Basketball-specific scouting report — full game prep intelligence."""
    total = _total_plays(tendency_summary)
    if total < 5:
        return [{
            "heading": "Not Enough Possessions to Analyze Yet",
            "insight_type": "tendency",
            "body": (
                f"This report was generated from {total} tagged event"
                f"{'s' if total != 1 else ''}. Tendency analysis needs more possessions — "
                f"ideally a full game (60+ possessions), not highlight clips.\n\n"
                f"Import full game film and let AI auto-detection tag the possessions, then regenerate."
            ),
        }]

    off = tendency_summary.get("offense_plays", 0)
    def_plays = tendency_summary.get("defense_plays", 0)
    scouting = tendency_summary.get("scouting", {}) or {}

    # Six priority categories (Category 1 heaviest) + auto game-plan, then
    # film-depth sections that are appended ONLY when their data exists.
    sections_spec = _bball_sections(scouting, tendency_summary)

    section_outline = "\n".join(
        f"{i+1}. \"{s['heading']}\" (insight_type: \"{s['insight_type']}\")\n   Instructions: {s['instructions']}"
        for i, s in enumerate(sections_spec)
    )

    prompt = f"""Sport: Basketball
Report Type: {report_type}
Sample Size: {total} total events (offense: {off}, defense: {def_plays})

TENDENCY DATA:
{json.dumps(tendency_summary, indent=2)}

Write a complete basketball opponent scouting report as a JSON array. Each element: {{"heading": "...", "insight_type": "...", "body": "..."}}.

SECTIONS (write every one in order):
{section_outline}

BODY FORMAT (a coach scans this fast, do NOT write essays):
- Each section body = ONE short lead sentence, then a blank line, then BULLET POINTS. Put each bullet on its own line starting with "- ".
- One tendency or one action per bullet, one sentence each.
- Bold key numbers with **double asterisks**, e.g. "- **54% FG** on the pick and roll (23 possessions), hedge hard."
- Every bullet cites attempt counts alongside percentages.
- Lead each section (the one sentence) with the most actionable finding.
- Separate the lead sentence from the bullets with a blank line (\\n\\n) so they format as a list.
- Do not write multi-sentence paragraphs. Default to bullets everywhere.

Return ONLY the JSON array, nothing else."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=7000,
        system=SYSTEM_PROMPT_BASKETBALL,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    sections = _parse_report_sections(raw)

    if is_trial:
        sections.append({
            "heading": "Trial Report",
            "insight_type": "tendency",
            "body": "This is a trial report. Upgrade at coachlenz.com to unlock full reports and exports.",
        })
    return sections


async def suggest_tags(event_description: str) -> List[str]:
    message = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"Suggest 3-5 short tags for this football/sports play: {event_description}. Return only a JSON array of strings.",
        }],
    )
    try:
        return json.loads(message.content[0].text)
    except Exception:
        return []
