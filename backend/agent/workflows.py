"""
Orchestration: multi-step workflows that chain the read-only tools, then hand the
collected signals to the structured summarizer. This is the "chain steps" surface,
each step is a real tool call whose output feeds the next, ending in a validated,
schema-constrained verdict the software can act on.
"""
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent import tools as toolkit
from backend.agent import structured


async def account_health(db: AsyncSession, organization_id: str) -> Dict[str, Any]:
    """Run retention -> conversion -> credit economics, then summarize into a
    validated AccountHealthSummary. Returns the raw steps and the structured verdict."""
    ctx = toolkit.ToolContext(db=db, organization_id=organization_id, is_admin=True)

    steps: Dict[str, Any] = {}
    for name in ("retention_gate", "conversion_funnel", "credit_costs"):
        tool = toolkit.by_name(name)
        try:
            steps[name] = await tool.handler(ctx, {})
        except Exception as e:
            steps[name] = {"error": str(e)}

    verdict = await structured.summarize_account_health({
        "retention": steps.get("retention_gate"),
        "conversion": steps.get("conversion_funnel"),
        "credit_costs": steps.get("credit_costs"),
    })
    return {"workflow": "account_health", "steps": steps, "verdict": verdict}
