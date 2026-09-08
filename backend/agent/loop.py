"""
CoachLenz Operator agent loop: a real Anthropic tool-use loop over the read-only tool
registry (agent/tools.py). UATP throughout: identity in the system prompt, an action
log of every tool call with a confidence note, a DRY_RUN mode, and honest failure
(a tool error is reported, never swallowed into a fake answer).

Read-only by construction, so no human-approval gate is required; if a mutating tool
is ever added, gate it before enabling it here.
"""
import json
import pathlib
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.agent import tools as toolkit

AGENT_MODEL = "claude-sonnet-4-6"
MAX_STEPS = 6
_PROMPT = (pathlib.Path(__file__).parent / "prompts" / "operator.md").read_text(encoding="utf-8")


async def run_agent(db: AsyncSession, message: str, *, is_admin: bool = False,
                    organization_id: Optional[str] = None, user_id: Optional[str] = None,
                    dry_run: bool = False, max_steps: int = MAX_STEPS) -> Dict[str, Any]:
    """Run the operator agent for one operator message. Returns the final text, the
    UATP action log (one entry per tool call), and the tools that were available."""
    available = toolkit.tools_for(is_admin)
    schema = toolkit.anthropic_schema(available)

    # UATP: DRY_RUN simulates without calling the model or the tools.
    if dry_run:
        return {"agent": "CoachLenz Operator", "dry_run": True, "final_text": None,
                "available_tools": [t["name"] for t in schema],
                "action_log": [], "note": "DRY_RUN: no model or tool calls were made."}

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    ctx = toolkit.ToolContext(db=db, organization_id=organization_id, user_id=user_id, is_admin=is_admin)

    system = [{"type": "text", "text": _PROMPT, "cache_control": {"type": "ephemeral"}}]
    messages: List[Dict[str, Any]] = [{"role": "user", "content": message}]
    action_log: List[Dict[str, Any]] = []
    final_text = None

    for _step in range(max_steps):
        resp = await client.messages.create(
            model=AGENT_MODEL, max_tokens=1500, system=system,
            tools=schema, messages=messages,
        )
        # Collect any text + tool_use blocks from this turn.
        text_bits = [b.text for b in resp.content if b.type == "text"]
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if text_bits:
            final_text = "\n".join(text_bits)

        if resp.stop_reason != "tool_use" or not tool_uses:
            break

        messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        results = []
        for tu in tool_uses:
            tool = toolkit.by_name(tu.name)
            entry = {"tool": tu.name, "input": tu.input}
            if tool is None or (tool.admin_only and not is_admin):
                entry.update({"ok": False, "error": "tool not available"})
                results.append({"type": "tool_result", "tool_use_id": tu.id,
                                "content": "Error: tool not available", "is_error": True})
            else:
                try:
                    out = await tool.handler(ctx, tu.input or {})
                    entry.update({"ok": True, "confidence": "high", "result": out})
                    results.append({"type": "tool_result", "tool_use_id": tu.id,
                                    "content": json.dumps(out, default=str)})
                except Exception as e:  # UATP: honest failure, never a fake result
                    entry.update({"ok": False, "confidence": "unknown", "error": str(e)})
                    results.append({"type": "tool_result", "tool_use_id": tu.id,
                                    "content": f"Error: {e}", "is_error": True})
            action_log.append(entry)
        messages.append({"role": "user", "content": results})

    return {"agent": "CoachLenz Operator", "dry_run": False, "final_text": final_text,
            "available_tools": [t["name"] for t in schema], "action_log": action_log}
