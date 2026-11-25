-- Reverse of 057_marketing_lead_waitlist.sql. The migrator ignores *.down.sql.
-- Run by hand only when rolling the schema back:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/057_marketing_lead_waitlist.down.sql
--
-- WARNING: this drops the waitlist columns, which loses data by design:
-- consent version, confirmed_at, unsubscribed_at and unsubscribe_token among
-- them. Without unsubscribed_at, people who opted out look subscribed again.
-- Do not run this against production without Jason's written approval. Roll
-- back 060, 059, 058 first (reverse order). email and source from 045 stay.
--
-- Backup: every dropped column is first copied, with id and email, to
-- marketing_leads_bak_057_<UTC timestamp>. Restore with UPDATE ... FROM that
-- copy after re-applying 057. One transaction, so a failed backup drops nothing.

BEGIN;

DO $$
DECLARE
    stamp text := to_char(now() AT TIME ZONE 'UTC', 'YYYYMMDD_HH24MISS');
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketing_leads' AND column_name = 'unsubscribe_token'
    ) THEN
        RETURN;
    END IF;
    EXECUTE format(
        'CREATE TABLE %I AS SELECT id, email, first_name, school, sport, role, role_branch, '
        'consent_text_version, lead_magnet, utm_source, utm_medium, utm_campaign, utm_content, '
        'utm_term, referrer, landing_path, ref_code, confirm_token_hash, confirm_sent_at, '
        'confirmed_at, unsubscribed_at, unsubscribe_token, resend_contact_id, has_account '
        'FROM marketing_leads',
        'marketing_leads_bak_057_' || stamp
    );
END $$;

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

-- Let the migrator re-apply 057 on the next deploy.
DELETE FROM schema_migrations WHERE filename = '057_marketing_lead_waitlist.sql';

COMMIT;
