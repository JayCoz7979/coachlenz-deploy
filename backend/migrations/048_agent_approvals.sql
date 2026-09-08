-- Human-approval gate for agent-initiated mutating actions. A risky action the agent
-- proposes is queued here as 'pending' and only executed after a human approves it
-- (see routers/agent.py). The read-only tool registry stays read-only; anything that
-- changes data goes through this gate.

CREATE TABLE IF NOT EXISTS agent_approvals (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    action           text NOT NULL,                       -- e.g. 'set_learning_loop_mode'
    args             jsonb NOT NULL DEFAULT '{}'::jsonb,
    status           text NOT NULL DEFAULT 'pending',     -- pending | approved | rejected | executed
    requested_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    decided_by       uuid REFERENCES users(id) ON DELETE SET NULL,
    result           text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    decided_at       timestamptz
);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_org_status ON agent_approvals (organization_id, status);
