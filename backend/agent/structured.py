"""
Structured model output the software acts on. The model is forced to answer through a
single schema-constrained tool (account_health_report), and the result is validated
against a Pydantic model before any code uses it, a bad answer fails validation rather
than driving the product with garbage.
"""
import json
import pathlib
from typing import Any, Dict

from pydantic import BaseModel, ValidationError

from backend.config import settings

AGENT_MODEL = "claude-sonnet-4-6"
_PROMPT = (pathlib.Path(__file__).parent / "prompts" / "health_summarizer.md").read_text(encoding="utf-8")


class AccountHealthSummary(BaseModel):
    """The schema the model must fill and the software then acts on."""
    headline: str
    retention_state: str
    conversion_state: str
    top_risk: str
    recommended_next_step: str
    confidence: str  # high | medium | low


_TOOL = {
    "name": "account_health_report",
    "description": "Return the account health verdict as structured fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "retention_state": {"type": "string"},
            "conversion_state": {"type": "string"},
            "top_risk": {"type": "string"},
            "recommended_next_step": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["headline", "retention_state", "conversion_state", "top_risk",
                     "recommended_next_step", "confidence"],
        "additionalProperties": False,
    },
}


async def summarize_account_health(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Call the model with tool_choice forcing the schema, then validate. Returns
    {ok, summary|error}. Never raises into the caller."""
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        resp = await client.messages.create(
            model=AGENT_MODEL, max_tokens=700,
            system=[{"type": "text", "text": _PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "account_health_report"},
            messages=[{"role": "user", "content": json.dumps(inputs, default=str)}],
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            return {"ok": False, "error": "model returned no structured tool call"}
        summary = AccountHealthSummary.model_validate(block.input)  # structured-output guard
        return {"ok": True, "summary": summary.model_dump()}
    except ValidationError as e:
        return {"ok": False, "error": f"structured output failed validation: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
