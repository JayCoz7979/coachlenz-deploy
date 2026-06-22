import json
import anthropic
from typing import List, Dict, Any
from backend.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-6"


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

SECTION FORMATS:
- Body paragraphs: 2-3 punchy paragraphs per section, not walls of text
- Include inline counts: never say "often" when you can say "7 of 9 times"
- Flag anomalies: if a tendency disappears in the red zone vs. open field, say so
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

SECTION FORMATS:
- 2-3 punchy paragraphs per section, not walls of text
- Include counts: never say "often" when you can say "14 of 19 possessions"
- Call out hot zones AND cold zones — both matter for defensive positioning
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

    # Build sections based on available data
    sections_spec = [
        {
            "heading": "Executive Summary",
            "insight_type": "tendency",
            "instructions": (
                "2-3 paragraph overview of the opponent's identity. "
                "Lead with their offensive philosophy (run-first? spread? power?), then defensive identity, then special teams threat level. "
                "End with the single most important tendency the staff needs to know going into game week."
            ),
        }
    ]

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
            "heading": "Opponent Special Teams",
            "insight_type": "tendency",
            "instructions": (
                "Cover: FG range and accuracy (by distance range if data has it), "
                "punt operation (avg distance, hangtime tendencies), "
                "kickoff approach, "
                "return threat (avg yards, explosive returns), "
                "trick/fake play tendency. "
                "Advise on: field goal block chances, return opportunities, and fake alert situations."
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

BODY FORMAT:
- Plain text only, paragraphs separated by \\n\\n
- Always cite play counts alongside percentages
- Lead each section with the most exploitable finding
- EXPLOITABLE PATTERNS sections: use bullet points starting with •

Return ONLY the JSON array, nothing else."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        system=SYSTEM_PROMPT_FOOTBALL,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        sections = [
            {
                "heading": s.get("heading", "Analysis"),
                "insight_type": s.get("insight_type", "tendency"),
                "body": s.get("body", ""),
            }
            for s in parsed if isinstance(s, dict)
        ]
        if not sections:
            raise ValueError("empty")
    except Exception:
        sections = [{"heading": "Tendency Analysis", "insight_type": "tendency", "body": raw}]

    if is_trial:
        sections.append({
            "heading": "Trial Report",
            "insight_type": "tendency",
            "body": "This is a trial report. Upgrade at coachlenz.com to unlock full reports and exports.",
        })
    return sections


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

    sections_spec = [
        {
            "heading": "Executive Summary",
            "insight_type": "tendency",
            "instructions": (
                "2-3 paragraph overview of this team's identity on both ends. "
                "Lead with their offensive system (PnR-heavy? Iso? Motion? Transition-first?), "
                "then their defensive scheme and what makes them hard to score against. "
                "End with the single most important thing the staff needs to know going into game week."
            ),
        },
        {
            "heading": "Shot Chart Intelligence",
            "insight_type": "tendency",
            "instructions": (
                "Use shot_zone_map.zones to build a complete shooting profile. "
                "Name every zone with data: attempts, FG%, and pct_of_all_shots. "
                "Identify: hottest_zone (where they score most efficiently) AND most_frequent_zone (where they attack most). "
                "Use field side distribution — do they favor left or right? Do they hunt corner 3s? "
                "Call out COLD zones (high attempt rate, low FG%) — these are traps to force them into. "
                "Use shooting_overview: overall split between paint, mid-range, and 3PT with FG% on each. "
                "Advise: where should our defense funnel them? What area must we take away?"
            ),
        },
        {
            "heading": "Offensive System Breakdown",
            "insight_type": "tendency",
            "instructions": (
                "Use shot_creation.by_play_action and pick_and_roll to identify their primary offensive system. "
                "PnR: cite total possessions, roll vs pop split, preferred screen position, FG%, turnovers. "
                "Isolation: cite frequency, zones they iso from, FG%. "
                "Post up: if post_up has data, cite FG% and kick-out frequency. "
                "Use screen_usage: what screens do they run most and how effective are they? "
                "Use transition: how often do they push pace? Primary break FG%? "
                "Use inbound_plays: do they score off BLOB/SLOB sets? Cite most used set and action. "
                "Advise: what scheme stops their primary action? How do we disrupt their sets?"
            ),
        },
        {
            "heading": "Inbound Play Intelligence — Offense (BLOB & SLOB)",
            "insight_type": "tendency",
            "instructions": (
                "This is one of the most exploitable areas in basketball — teams run the same inbound sets repeatedly. "
                "Use inbound_plays.blob and inbound_plays.slob for full detail. "
                "BLOB (Baseline Out of Bounds): most used set (most_used_set), best FG% set (best_set). "
                "Most used primary action (most_used_action) and how it creates a shot. "
                "Where do they score from? (hottest_zone, most_targeted_zone). "
                "How many late-game and after-timeout BLOBs? "
                "What defense coverage have they faced, and which leaves them open? "
                "SLOB (Sideline Out of Bounds): same depth — most used set, primary action, scoring zone. "
                "Preferred inbound_side (left or right sideline). "
                "After-timeout SLOBs — what play do they call coming out of a timeout? "
                "Most dangerous play overall: the set + action combo with highest made shot rate. "
                "Advise defense: exactly how to take away their best BLOB and best SLOB. "
                "Only include BLOB/SLOB sections if inbound_plays.blob.total > 0 or slob.total > 0."
            ),
        },
        {
            "heading": "Inbound Defense — How They Defend BOB/SLOB",
            "insight_type": "defense",
            "instructions": (
                "Use inbound_defense to understand how OUR offense attacks their inbound defense. "
                "Primary coverage (Man Switch, Man No Switch, Zone, etc.). "
                "Coverage distribution — are they consistent or mixed? "
                "FG% they allow on inbound plays (fg_pct_allowed). "
                "Zones they surrender (zones_surrendered + most_vulnerable_zone). "
                "Advise OC: design specific BLOB and SLOB sets that attack their coverage. "
                "For example: 'They Man No Switch on BLOBs — run Box set with cross screen. They will NOT switch, so the mismatch exists every time.' "
                "Only include if inbound_defense.total > 0."
            ),
        },
        {
            "heading": "Drive, Paint, and Kick-Out Patterns",
            "insight_type": "tendency",
            "instructions": (
                "Use paint_and_drive: how many paint touches per game? Kick-out rate? Drive-and-kick count? Paint FG%? "
                "This tells you: do they use paint touches to score or to create kick-out 3s? "
                "If high kick_out_count relative to paint_touch_count, their best offense is drive-kick — "
                "advise closing out hard on perimeter after any drive. "
                "If high paint FG%, they finish — advise sending help on every drive. "
                "Use shot_clock: do they get easy early-clock paint looks or grind to late-clock situations? "
                "Advise specifically: contest at rim or help and recover?"
            ),
        },
        {
            "heading": "Ball Screen Defense Attack Plan",
            "insight_type": "defense",
            "instructions": (
                "Use ball_screen_defense to understand how THEY defend ball screens — this is how OUR offense attacks them. "
                "Primary hedge style: Hard Hedge, Drop, Switch, ICE, or Blitz? "
                "What does each hedge style leave open? "
                "Hard Hedge → screener slips or roll early, ball handler pull-up off the hedge. "
                "Drop Coverage → ball handler can pull up at foul line, mid-range. "
                "Switch → attack mismatches, post the smaller defender. "
                "ICE/Push → middle of the floor opens, reverse the pick. "
                "Blitz/Double → kick out to open 3s, skip pass. "
                "Use hedge_distribution to show if they are consistent or mixed. "
                "Advise OC: design 3 specific plays that attack their primary hedge style."
            ),
        },
        {
            "heading": "Defensive Scheme & Tendencies",
            "insight_type": "defense",
            "instructions": (
                "Use defensive_scheme: primary scheme (Man, Zone 2-3, etc.), man vs zone pct, press count. "
                "Do they change scheme by quarter? (cite quarters_used for each scheme). "
                "Use ball_screen_defense.help_defense and deny_style: how do they handle off-ball? "
                "Full denial tells us to back-cut. Open/Sag tells us to spot up. Collapsing help tells us to kick out. "
                "press_triggers: if they press, when? After made baskets? Always? "
                "Advise: what offensive actions, formations, and concepts break their primary defensive scheme?"
            ),
        },
        {
            "heading": "Situational Intelligence",
            "insight_type": "tendency",
            "instructions": (
                "Use quarter_breakdown: which quarter do they shoot best/worst? When do turnovers spike? "
                "Use shot_clock: are they disciplined (mostly early/mid clock) or chaotic (high late-clock %)? "
                "Late-clock FG% vs early-clock FG% — does shot clock pressure hurt them? "
                "Use game_script: do their tendencies change when leading vs trailing? "
                "If they jack up 3s when trailing, deny the 3-point line in late-game situations. "
                "If they become turnover-prone when losing, apply pressure late. "
                "Only cite game_script if data covers 2+ margin situations."
            ),
        },
        {
            "heading": "EXPLOITABLE PATTERNS — Offense",
            "insight_type": "tendency",
            "instructions": (
                "Bullet-point intelligence brief for the defensive game plan. "
                "List 5-7 specific, exploitable offensive tendencies with the defensive counter. Format:\n"
                "• [TENDENCY]: [what they do and how often] → [COUNTER]: [specific defensive adjustment]\n"
                "Examples:\n"
                "• CORNER 3 HUNTING: 34% of shots come from corner 3 zones (Left: 18%, Right: 16%), 44% FG — they run baseline drift after every PnR → Shade help defender to corner, contest all corner catches\n"
                "• LATE SHOT CLOCK: 28% of possessions end in late shot clock shots (14 of 50), only 31% FG — they don't have a bailout play → Play disciplined defense, no reach fouls, force late clock\n"
                "Only include tendencies with 5+ instances. This is the most important section."
            ),
        },
        {
            "heading": "EXPLOITABLE PATTERNS — Defense",
            "insight_type": "tendency",
            "instructions": (
                "Bullet-point intelligence brief for the offensive game plan. "
                "List 4-6 specific vulnerabilities in their defense with the offensive attack. Format:\n"
                "• [VULNERABILITY]: [what they do and why it's exploitable] → [ATTACK]: [specific action]\n"
                "Examples:\n"
                "• DROP COVERAGE: They drop on all ball screens (18/22 PnR coverages) → Ball handler pull-up at foul line, shoot over the drop\n"
                "• ZONE WEAKNESS: Their 2-3 zone gives up elbow mid-range and high post consistently → Run Horns sets, attack the elbow before the zone sets\n"
                "Only include vulnerabilities with enough film evidence."
            ),
        },
        {
            "heading": "Game Plan Priorities",
            "insight_type": "tendency",
            "instructions": (
                "Numbered priority list — the 6-8 most important game-plan items for this opponent. "
                "Specific and actionable, not generic. Number them by priority. "
                "Format: 1. [O/D]: [specific action tied directly to a tendency from the data]"
            ),
        },
    ]

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

BODY FORMAT:
- Plain text, paragraphs separated by \\n\\n
- Always cite attempt counts alongside percentages
- EXPLOITABLE PATTERNS sections: bullet points starting with •
- Lead every section with the most actionable finding

Return ONLY the JSON array, nothing else."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=7000,
        system=SYSTEM_PROMPT_BASKETBALL,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        sections = [
            {
                "heading": s.get("heading", "Analysis"),
                "insight_type": s.get("insight_type", "tendency"),
                "body": s.get("body", ""),
            }
            for s in parsed if isinstance(s, dict)
        ]
        if not sections:
            raise ValueError("empty")
    except Exception:
        sections = [{"heading": "Basketball Analysis", "insight_type": "tendency", "body": raw}]

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
