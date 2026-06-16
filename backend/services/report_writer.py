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


async def generate_prose_sections(
    sport: str,
    tendency_summary: Dict[str, Any],
    report_type: str,
    is_trial: bool = False,
) -> List[Dict[str, Any]]:
    """Returns sections shaped as [{heading, body, insight_type}] for the report viewer."""
    plays = _total_plays(tendency_summary)

    # Not enough data — return one clear, helpful section instead of empty cards.
    if plays < 5:
        return [{
            "heading": "Not Enough Plays to Analyze Yet",
            "insight_type": "tendency",
            "body": (
                f"This report was generated from {plays} tagged play"
                f"{'s' if plays != 1 else ''}. Tendency analysis needs more plays to find "
                f"reliable patterns — ideally full game film (60+ plays), not a highlight reel.\n\n"
                f"To get a strong report: import full game film (every play, not just highlights), "
                f"let AI auto-detection tag the plays, then generate the report again. Highlight "
                f"reels are great for quick clips but don't contain enough of the game to reveal "
                f"an opponent's tendencies."
            ),
        }]

    off_plays = int(tendency_summary.get("offense_plays", 0) or 0)
    def_plays = int(tendency_summary.get("defense_plays", 0) or 0)
    st_plays = int(tendency_summary.get("special_teams_plays", 0) or 0)

    # Build the section outline based on which phases have data.
    outline = ['1. "Executive Summary" (insight_type: "tendency") — scouting overview of the opponent across all three phases']
    n = 2
    if off_plays >= 5:
        outline.append(f'{n}. "Opponent Offense — Tendencies" (insight_type: "run") — run/pass split, down & distance, formations, personnel; how OUR DEFENSE should prepare')
        n += 1
        outline.append(f'{n}. "Opponent Offense — Situational" (insight_type: "red_zone") — 3rd down, red zone, short yardage tendencies')
        n += 1
    if def_plays >= 5:
        outline.append(f'{n}. "Opponent Defense — Coverages & Fronts" (insight_type: "defense") — fronts, coverages, blitz rate; how OUR OFFENSE should attack it')
        n += 1
        outline.append(f'{n}. "Opponent Defense — Situational" (insight_type: "defense") — coverage by down, blitz on passing downs')
        n += 1
    if st_plays >= 3:
        outline.append(f'{n}. "Opponent Special Teams" (insight_type: "tendency") — FG range/accuracy, punt/kickoff tendencies, return threats, fakes/trick risk; how OUR special teams should prepare')
        n += 1
    outline.append(f'{n}. "Recommended Game Plan" (insight_type: "red_zone") — concrete, actionable adjustments across offense, defense, and special teams')

    system = (
        "You are an expert football analyst for CoachLenz writing an OPPONENT SCOUTING report. "
        "Write clear, actionable analysis for coaches in direct, professional language. "
        "Offensive data = the opponent on offense (advise how to defend them). "
        "Defensive data = the opponent on defense (advise how to attack them). "
        "Focus on specific, exploitable patterns backed only by the data provided."
    )
    prompt = f"""Sport: {sport}
Report Type: {report_type}
Total plays: {plays} (opponent offense: {off_plays}, opponent defense: {def_plays}, special teams: {st_plays})

Tendency Data (JSON):
{json.dumps(tendency_summary, indent=2)}

Write an opponent scouting report as a JSON array of sections, using EXACTLY these sections in order:
{chr(10).join(outline)}

Each section is an object: {{"heading": "...", "insight_type": "...", "body": "..."}}.
The "body" is multi-paragraph plain text (use \\n\\n between paragraphs). Cite real numbers/percentages
from the data. Do NOT invent data not present. If a side has little data, say so briefly.

Return ONLY the JSON array, nothing else."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
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
        # Never return broken/empty cards — fall back to the raw prose in one section.
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
    import json
    try:
        return json.loads(message.content[0].text)
    except Exception:
        return []
