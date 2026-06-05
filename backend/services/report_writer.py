import anthropic
from typing import List, Dict, Any
from backend.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

WATERMARK = "\n\n[TRIAL REPORT — Upgrade at coachlenz.com to remove watermarks]"

async def generate_prose_sections(
    sport: str,
    tendency_summary: Dict[str, Any],
    report_type: str,
    is_trial: bool = False,
) -> List[Dict[str, Any]]:
    system = (
        "You are an expert football and sports analyst assistant for CoachLenz. "
        "Write clear, actionable tendency analysis for coaches. "
        "Use direct, professional language. Focus on exploitable patterns."
    )
    prompt = f"""
Sport: {sport}
Report Type: {report_type}

Tendency Data:
{tendency_summary}

Write a comprehensive tendency analysis report with the following sections:
1. Executive Summary (2-3 paragraphs)
2. Key Tendencies & Patterns
3. Situational Analysis
4. Recommended Adjustments

Format each section clearly. Be specific and actionable.
"""
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    prose = message.content[0].text
    if is_trial:
        prose += WATERMARK
    return [{"type": "prose", "content": prose}]

async def suggest_tags(event_description: str) -> List[str]:
    message = client.messages.create(
        model="claude-sonnet-4-5",
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
