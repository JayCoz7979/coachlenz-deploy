-- Conversion funnel instrumentation + non-converter lead capture.
--
-- First-party only, no third-party trackers. funnel_events is platform analytics
-- read by the founder, so it is intentionally NOT per-tenant: the anonymous
-- top-of-funnel rows (a visitor before signup) have no organization. No PII is
-- stored here; anon_id is a random client id from localStorage, not an identity.
--
-- The gate metric is visitor -> completed signup. Steps:
--   landing_view -> cta_click -> signup_view -> signup_start -> signup_complete
-- The three top steps are anonymous (counted by DISTINCT anon_id so refreshes do
-- not inflate); the two signup steps are emitted server-side, one row per account.

CREATE TABLE IF NOT EXISTS funnel_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    anon_id         text,                 -- random client id; null on server-emitted rows
    event           text NOT NULL,        -- landing_view|cta_click|signup_view|signup_start|signup_complete
    path            text,
    organization_id uuid REFERENCES organizations(id) ON DELETE SET NULL,
    meta            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_funnel_event_time ON funnel_events (event, created_at);
CREATE INDEX IF NOT EXISTS ix_funnel_anon ON funnel_events (anon_id);

-- Intent captured from visitors who do not sign up on the first visit, so they can
-- be nurtured rather than lost. The email is volunteered by the visitor.
CREATE TABLE IF NOT EXISTS marketing_leads (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text NOT NULL,
    source      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_marketing_lead_email ON marketing_leads (lower(email));
