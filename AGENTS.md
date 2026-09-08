# AGENTS.md: CoachLenz for agents

CoachLenz is an AI film-analyst OS for coaches (FastAPI backend, Next.js frontend,
Railway Postgres + Cloudflare R2). This file tells an AI agent how to operate it
without a human.

## Machine surfaces
- **HTTP API**: FastAPI. A machine-readable description is committed at
  `backend/openapi.json` and served live at `/openapi.json`.
- **MCP server**: `backend/mcp_server/server.py` (stdio). Run it with
  `python -m backend.mcp_server.server` (needs `pip install mcp`). Discovery: root
  `mcp.json` and `backend/mcp_server/server-card.json`.

## The CoachLenz Operator agent
A read-only analyst agent. In-app entrypoint: `POST /agent/run` (admin-gated,
`{message, dry_run}`); tool list at `GET /agent/tools`. Loop: `backend/agent/loop.py`.
Tools: `backend/agent/tools.py`. System prompt: `backend/agent/prompts/operator.md`.

### Tools (all READ-ONLY, safe to call without approval)
- `credit_costs`: per-analysis credit costs, bundles, margin floor.
- `margin_check`: does a measured per-run cost hold the 65% margin floor for N credits.
- `list_recent_games`: the caller org's recent games.
- `retention_gate`: platform retention summary vs the gate (admin).
- `conversion_funnel`: platform visitor-to-signup funnel + biggest drop-off (admin).
- `list_reports`: the caller org's recent generated reports.
- `credit_balance`: the caller org's analysis-credit wallet balance.
- `learning_summary`: the org's per-account learning adjustments by status.

## Orchestration
`POST /agent/workflow/account-health` chains retention, conversion, and credit
economics, then produces a schema-validated `AccountHealthSummary`
(`backend/agent/structured.py`, model output validated by Pydantic before use).
Workflow code: `backend/agent/workflows.py`.

## Mutating actions (human-gated)
Write actions are never in the read-only tool registry. The agent PROPOSES one via
`POST /agent/actions/*` (e.g. `learning-mode`), which queues an `agent_approvals` row.
A human approves at `POST /agent/approvals/{id}/approve` (or rejects), and only then
does it execute. List pending at `GET /agent/approvals`.

## UATP (transparency contract, required)
Every agent action discloses identity ("CoachLenz Operator"), logs each tool call with
a confidence note (the `action_log` in the run result), supports a `dry_run` staging
mode, and reports tool failures honestly instead of fabricating a result.

## Safety rules for extending the agent
- Tools here are read-only. **Do not add a write/send/spend tool to the registry
  without a human-approval gate** in front of it. The registry is the single source of
  truth shared by the API loop and the MCP server, so a mutating tool would be exposed
  everywhere at once.
- The free Live Game Logger and film analysis behavior must not change; the agent only
  reads and reports.

Powered by [Cosby AI Solutions](https://cosbyaisolutions.com).
