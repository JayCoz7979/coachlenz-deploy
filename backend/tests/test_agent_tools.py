"""
Operator agent tool registry (pure parts): the read-only tools, their schemas, the
admin filter, and the two no-DB tools' math. The DB-backed tools are exercised in the
integration/live paths; here we lock the registry contract.
"""
import asyncio

from backend.agent import tools as T


def test_registry_shapes_are_valid_tool_use_schemas():
    schema = T.anthropic_schema(T.TOOLS)
    assert len(schema) == len(T.TOOLS)
    for s in schema:
        assert set(s.keys()) == {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"
        assert isinstance(s["description"], str) and s["description"]


def test_admin_only_tools_are_hidden_from_non_admins():
    admin_names = {t.name for t in T.tools_for(is_admin=True)}
    public_names = {t.name for t in T.tools_for(is_admin=False)}
    assert {"retention_gate", "conversion_funnel"} <= admin_names
    assert not ({"retention_gate", "conversion_funnel"} & public_names)
    # The safe read tools are available to everyone.
    assert {"credit_costs", "margin_check", "list_recent_games"} <= public_names


def test_by_name_and_all_tools_are_read_only():
    assert T.by_name("credit_costs") is not None
    assert T.by_name("nope") is None
    # No tool name implies a mutation (defense against a future write tool sneaking in).
    for t in T.TOOLS:
        assert not any(w in t.name for w in ("create", "update", "delete", "send", "deploy", "spend", "charge"))


def test_credit_costs_tool_returns_locked_numbers():
    ctx = T.ToolContext(db=None)
    out = asyncio.run(T.by_name("credit_costs").handler(ctx, {}))
    assert out["standard"]["football"] == 29
    assert out["deep_grade"]["football"] == 55
    assert out["margin_floor"] == 0.65


def test_margin_check_tool_math():
    ctx = T.ToolContext(db=None)
    out = asyncio.run(T.by_name("margin_check").handler(ctx, {"avg_cost_usd": 10.0, "credits": 55}))
    assert out["revenue_at_floor_usd"] == 38.5
    assert out["max_cogs_to_hold_floor_usd"] == 13.475
    assert out["verdict"] == "pass"
