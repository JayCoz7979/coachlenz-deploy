-- Reverse of 057_marketing_lead_waitlist.sql. The migrator ignores *.down.sql.
-- Run this by hand only when rolling the schema back:
--   psql "$DATABASE_URL" -f backend/migrations/057_marketing_lead_waitlist.down.sql
--
-- Dropping these columns deletes the waitlist details already collected.
-- The email and source columns from migration 045 stay.

ALTER TABLE marketing_leads
    DROP COLUMN IF EXISTS email_consent_version,
    DROP COLUMN IF EXISTS email_consent_at,
    DROP COLUMN IF EXISTS utm_campaign,
    DROP COLUMN IF EXISTS utm_medium,
    DROP COLUMN IF EXISTS utm_source,
    DROP COLUMN IF EXISTS lead_magnet,
    DROP COLUMN IF EXISTS role_other,
    DROP COLUMN IF EXISTS role,
    DROP COLUMN IF EXISTS sport,
    DROP COLUMN IF EXISTS school,
    DROP COLUMN IF EXISTS name;
