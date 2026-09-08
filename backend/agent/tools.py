"""
Read-only agent tools for the CoachLenz Operator agent + MCP server.

Every tool is READ-ONLY and safe: it reads existing data or computes from config, so
the agent can be run without a human-approval gate. Each tool has a JSON input schema
(so the model emits schema-constrained, structured tool calls) and returns a plain
dict the software can act on. Handlers reuse the same services the app uses, so the
agent can never diverge from product behavior.

To add a mutating tool later, gate it behind a human approval step (see AGENTS.md);
do not add write tools to this registry.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    """What a tool may use: a DB session and the calling operator's identity."""
    db: AsyncSession
    organization_id: Optional[str] = None
    user_id: Optional[str] = None
    is_admin: bool = False


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[ToolContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]
    admin_only: bool = False


# ── Pure tools (no DB) ─────────────────────────────────────────────────────────
async def _credit_costs(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.services import credits as c
    return {
        "standard": c.STANDARD_CREDITS,
        "deep_grade": c.DEEP_GRADE_CREDITS,
        "reanalysis": c.REANALYSIS_CREDITS,
        "bundles": {k: {"credits": cr, "price_cents": p} for k, (cr, p) in c.BUNDLES.items()},
        "margin_floor": c.MARGIN_FLOOR,
        "floor_credit_price": c.FLOOR_CREDIT_PRICE,
    }


async def _margin_check(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.services import credits as c
    credits = int(args["credits"])
    cost = float(args["avg_cost_usd"])
    return {
        "credits": credits,
        "avg_cost_usd": cost,
        "revenue_at_floor_usd": round(credits * c.FLOOR_CREDIT_PRICE, 4),
        "max_cogs_to_hold_floor_usd": c.max_cogs_at_floor(credits),
        "verdict": c.margin_verdict(cost, credits),
    }


# ── DB tools (read-only) ────────────────────────────────────────────────────────
async def _list_recent_games(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.models.game import Game
    if not ctx.organization_id:
        return {"error": "no organization in context"}
    limit = max(1, min(int(args.get("limit", 20)), 100))
    rows = (await ctx.db.execute(
        select(Game.id, Game.opponent, Game.title, Game.sport, Game.status, Game.created_at)
        .where(Game.organization_id == ctx.organization_id)
        .order_by(Game.created_at.desc()).limit(limit)
    )).all()
    return {"games": [{"id": str(r.id), "opponent": r.opponent or r.title, "sport": r.sport,
                       "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None}
                      for r in rows]}


async def _retention_gate(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.services import retention
    from backend.models.organization import Organization
    from backend.models.usage import AnalysisUsage
    orgs = (await ctx.db.execute(select(Organization.id, Organization.created_at))).all()
    runs = (await ctx.db.execute(select(AnalysisUsage.organization_id, AnalysisUsage.created_at))).all()
    return retention.build_cohorts(
        [{"id": o.id, "created_at": o.created_at} for o in orgs],
        [{"organization_id": r.organization_id, "created_at": r.created_at} for r in runs],
    )["summary"]


async def _conversion_funnel(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.services import funnel
    from backend.models.funnel import FunnelEvent
    rows = (await ctx.db.execute(
        select(FunnelEvent.event, FunnelEvent.anon_id, FunnelEvent.created_at, FunnelEvent.source)
    )).all()
    out = funnel.build_funnel([{"event": r.event, "anon_id": r.anon_id,
                                "created_at": r.created_at, "source": r.source} for r in rows])
    return {"visitor_to_signup": out["visitor_to_signup"], "gate": out["gate"],
            "steps": out["steps"], "biggest_drop": out["biggest_drop"]}


async def _list_reports(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.models.report import TendencyReport
    if not ctx.organization_id:
        return {"error": "no organization in context"}
    limit = max(1, min(int(args.get("limit", 20)), 100))
    rows = (await ctx.db.execute(
        select(TendencyReport.id, TendencyReport.title, TendencyReport.sport,
               TendencyReport.report_type, TendencyReport.generated_at)
        .where(TendencyReport.organization_id == ctx.organization_id)
        .order_by(TendencyReport.generated_at.desc().nullslast()).limit(limit)
    )).all()
    return {"reports": [{"id": str(r.id), "title": r.title, "sport": r.sport,
                         "type": r.report_type,
                         "generated_at": r.generated_at.isoformat() if r.generated_at else None}
                        for r in rows]}


async def _credit_balance(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.services import credits
    if not ctx.organization_id:
        return {"error": "no organization in context"}
    return await credits.balance(ctx.db, ctx.organization_id)


async def _learning_summary(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from backend.models.learning import AccountLearningAdjustment
    from sqlalchemy import func
    if not ctx.organization_id:
        return {"error": "no organization in context"}
    rows = (await ctx.db.execute(
        select(AccountLearningAdjustment.status, func.count())
        .where(AccountLearningAdjustment.organization_id == ctx.organization_id)
        .group_by(AccountLearningAdjustment.status)
    )).all()
    return {"learning_adjustments_by_status": {r[0]: r[1] for r in rows}}


TOOLS: List[Tool] = [
    Tool("credit_costs", "The credit cost of each analysis type, the credit bundles, and the margin floor. No arguments.",
         {"type": "object", "properties": {}, "additionalProperties": False}, _credit_costs),
    Tool("margin_check", "Check whether a measured average compute cost per run holds the 65% margin floor for an analysis of a given credit size.",
         {"type": "object", "properties": {
             "avg_cost_usd": {"type": "number", "description": "measured average USD cost per run"},
             "credits": {"type": "integer", "description": "credit cost of that analysis type"}},
          "required": ["avg_cost_usd", "credits"], "additionalProperties": False}, _margin_check),
    Tool("list_recent_games", "List the caller's organization's most recent games (id, opponent, sport, status).",
         {"type": "object", "properties": {"limit": {"type": "integer", "description": "max games (1-100)"}},
          "additionalProperties": False}, _list_recent_games),
    Tool("retention_gate", "The platform retention gate summary (matured-cohort return and activation rates vs the gate). Admin only.",
         {"type": "object", "properties": {}, "additionalProperties": False}, _retention_gate, admin_only=True),
    Tool("conversion_funnel", "The platform conversion funnel: visitor-to-signup rate, step counts, biggest drop-off, gate verdict. Admin only.",
         {"type": "object", "properties": {}, "additionalProperties": False}, _conversion_funnel, admin_only=True),
    Tool("list_reports", "List the caller's organization's most recent generated reports (id, title, sport, type).",
         {"type": "object", "properties": {"limit": {"type": "integer", "description": "max reports (1-100)"}},
          "additionalProperties": False}, _list_reports),
    Tool("credit_balance", "The caller's organization's current analysis-credit wallet balance.",
         {"type": "object", "properties": {}, "additionalProperties": False}, _credit_balance),
    Tool("learning_summary", "How many per-account learning adjustments the org has, by status (pending/active/rejected).",
         {"type": "object", "properties": {}, "additionalProperties": False}, _learning_summary),
]


def tools_for(is_admin: bool) -> List[Tool]:
    """Registry filtered by caller privilege (admin-only tools hidden from non-admins)."""
    return [t for t in TOOLS if (t.admin_only is False or is_admin)]


def anthropic_schema(tools: List[Tool]) -> List[Dict[str, Any]]:
    """The tools in Anthropic tool-use format."""
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]


def by_name(name: str) -> Optional[Tool]:
    for t in TOOLS:
        if t.name == name:
            return t
    return None
