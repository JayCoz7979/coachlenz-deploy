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


SYSTEM_PROMPT = """You are an elite football analyst writing an OPPONENT SCOUTING report for a head coach preparing for this week's game.

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


async def generate_prose_sections(
    sport: str,
    tendency_summary: Dict[str, Any],
    report_type: str,
    is_trial: bool = False,
) -> List[Dict[str, Any]]:
    """Returns sections shaped as [{heading, body, insight_type}] for the report viewer."""
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
        system=SYSTEM_PROMPT,
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
