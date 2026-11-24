-- Reverse of 057_marketing_lead_waitlist.sql. The migrator ignores *.down.sql.
-- Run by hand only when rolling the schema back:
--   psql "$DATABASE_URL" -f backend/migrations/057_marketing_lead_waitlist.down.sql
--
-- This drops the waitlist columns. email and source from migration 045 stay.

ALTER TABLE marketing_leads
    DROP COLUMN IF EXISTS has_account,
    DROP COLUMN IF EXISTS resend_contact_id,
    DROP COLUMN IF EXISTS unsubscribe_token,
    DROP COLUMN IF EXISTS unsubscribed_at,
    DROP COLUMN IF EXISTS confirmed_at,
    DROP COLUMN IF EXISTS confirm_sent_at,
    DROP COLUMN IF EXISTS confirm_token_hash,
    DROP COLUMN IF EXISTS ref_code,
    DROP COLUMN IF EXISTS landing_path,
    DROP COLUMN IF EXISTS referrer,
    DROP COLUMN IF EXISTS utm_term,
    DROP COLUMN IF EXISTS utm_content,
    DROP COLUMN IF EXISTS utm_campaign,
    DROP COLUMN IF EXISTS utm_medium,
    DROP COLUMN IF EXISTS utm_source,
    DROP COLUMN IF EXISTS lead_magnet,
    DROP COLUMN IF EXISTS consent_text_version,
    DROP COLUMN IF EXISTS role_branch,
    DROP COLUMN IF EXISTS role,
    DROP COLUMN IF EXISTS sport,
    DROP COLUMN IF EXISTS school,
    DROP COLUMN IF EXISTS first_name;
