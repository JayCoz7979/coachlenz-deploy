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

    system = (
        "You are an expert football and sports analyst for CoachLenz. "
        "Write clear, actionable tendency analysis for coaches in direct, professional language. "
        "Focus on specific, exploitable patterns backed by the data provided."
    )
    prompt = f"""Sport: {sport}
Report Type: {report_type}
Total plays analyzed: {plays}

Tendency Data (JSON):
{json.dumps(tendency_summary, indent=2)}

Write a tendency analysis report as a JSON array of sections. Use EXACTLY these four sections in order:
1. "Executive Summary" (insight_type: "tendency")
2. "Key Tendencies & Patterns" (insight_type: "run")
3. "Situational Analysis" (insight_type: "defense")
4. "Recommended Adjustments" (insight_type: "red_zone")

Each section is an object: {{"heading": "...", "insight_type": "...", "body": "..."}}.
The "body" is multi-paragraph plain text (use \\n\\n between paragraphs). Be specific to the data —
cite real numbers/percentages from the tendency data. Do not invent data not present.

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
