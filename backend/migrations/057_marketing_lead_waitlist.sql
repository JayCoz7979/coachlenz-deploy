-- Waitlist fields on the existing marketing_leads table.
--
-- POST /leads already stores a volunteered email and a source. The coming-soon
-- form also asks for a name, a role, an optional school and sport, and an
-- explicit email consent. UTM params and an optional lead_magnet slug are stored
-- so a later nurture sequence can tell where the person came from. This file
-- does not send email.
--
-- Every new column is nullable. Older "keep me posted" rows, and callers that
-- only send an email, keep working. The lower(email) unique index from
-- migration 045 is unchanged: a repeat address updates the volunteered fields
-- on that one row.
--
-- Numbered 057 because 056_games_r2_key_unique.sql belongs to the upload fix.
-- The runner applies 056, then 057, and ignores this file's .down.sql sibling.
--
-- Applied by the existing backend preDeploy runner (python -m backend.migrate).
-- Do not run this file by hand against production.
--
-- Down (run by hand, not by the migrator):
--   backend/migrations/057_marketing_lead_waitlist.down.sql

ALTER TABLE marketing_leads
    ADD COLUMN IF NOT EXISTS name text,
    ADD COLUMN IF NOT EXISTS school text,
    ADD COLUMN IF NOT EXISTS sport text,
    ADD COLUMN IF NOT EXISTS role text,
    ADD COLUMN IF NOT EXISTS role_other text,
    ADD COLUMN IF NOT EXISTS lead_magnet text,
    ADD COLUMN IF NOT EXISTS utm_source text,
    ADD COLUMN IF NOT EXISTS utm_medium text,
    ADD COLUMN IF NOT EXISTS utm_campaign text,
    ADD COLUMN IF NOT EXISTS email_consent_at timestamptz,
    ADD COLUMN IF NOT EXISTS email_consent_version text;
