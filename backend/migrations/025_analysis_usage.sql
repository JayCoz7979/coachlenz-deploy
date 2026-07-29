-- Analysis usage attribution (per coach) + AD-set per-coach monthly caps.
CREATE TABLE IF NOT EXISTS analysis_usage (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    sport text,
    analysis_type text,           -- fast | deep | deep_grade
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_usage_org ON analysis_usage (organization_id);
CREATE INDEX IF NOT EXISTS ix_analysis_usage_user_time ON analysis_usage (user_id, created_at);

CREATE TABLE IF NOT EXISTS coach_usage_limits (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    monthly_run_limit integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_coach_usage_limit UNIQUE (organization_id, user_id)
);
