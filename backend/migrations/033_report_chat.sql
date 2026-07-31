-- Report-scoped AI Coach Chat (Engine §13).
--
-- Every chat turn (coach question + Film Assistant answer) is stored against ONE
-- report and ONE org. The organization_id column is the isolation boundary — chat
-- context is scoped to a report the coach's own org owns, never across accounts
-- (isolation is app-layer, matching the rest of the platform; see docs/security).
--
-- Assistant rows carry UATP fields: a confidence score, whether the answer was
-- grounded in the film (answered=false => the "not enough of that in this film"
-- gap flag), the cited video cutups, and total_cost_usd to 6 decimals.

CREATE TABLE IF NOT EXISTS report_chat_messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    report_id       uuid NOT NULL REFERENCES tendency_reports(id) ON DELETE CASCADE,
    user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
    role            text NOT NULL,               -- 'user' | 'assistant'
    content         text NOT NULL,
    -- Assistant-only UATP columns (null on user rows).
    confidence      double precision,            -- 0..1; null = unknown
    answered        boolean,                     -- false => logged as a report gap flag
    cutups          jsonb NOT NULL DEFAULT '[]', -- video cutups the answer cites
    total_cost_usd  numeric(12,6),               -- UATP cost, 6 decimals
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Thread fetch: every message for a report in order.
CREATE INDEX IF NOT EXISTS ix_report_chat_report
    ON report_chat_messages (report_id, created_at);

-- Isolation-scoped lookups + cascade support.
CREATE INDEX IF NOT EXISTS ix_report_chat_org
    ON report_chat_messages (organization_id);

-- Gap-flag review: unanswered questions the film could not cover.
CREATE INDEX IF NOT EXISTS ix_report_chat_gap
    ON report_chat_messages (report_id)
    WHERE answered IS FALSE;
