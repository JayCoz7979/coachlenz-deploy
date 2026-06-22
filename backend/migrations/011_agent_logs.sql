-- UATP (Universal Agent Transparency Protocol) — agent action log.
-- Every agent decision is recorded here with reason, confidence, and level so
-- coaches can see exactly what the AI did, why, and how confident it was.
CREATE TABLE IF NOT EXISTS agent_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
    game_id uuid REFERENCES games(id) ON DELETE CASCADE,
    job_id uuid,
    agent_name text NOT NULL,
    agent_role text,
    phase text,
    action text NOT NULL,
    reason text,
    confidence double precision,
    level text NOT NULL DEFAULT 'info',  -- info | success | warn | escalation | error
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_game ON agent_logs (game_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_logs_org ON agent_logs (organization_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_logs_job ON agent_logs (job_id);
