-- Reverse of 058_marketing_consent_events.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/058_marketing_consent_events.down.sql
--
-- WARNING: this removes consent evidence (marketing_consent_events) and the
-- unsubscribe list (email_suppressions). Without the suppression list, people
-- who unsubscribed could be emailed again. Do not run this against production
-- without Jason's written approval. Roll back 060, 059 first (reverse order).
--
-- Backup: before anything is dropped, both tables are copied to
-- marketing_consent_events_bak_058_<UTC timestamp> and
-- email_suppressions_bak_058_<UTC timestamp>, and the dropped lead columns to
-- marketing_leads_bak_058_<UTC timestamp>. Restore with INSERT ... SELECT from
-- those copies after re-applying 058. Everything runs in one transaction, so a
-- failed backup drops nothing.

BEGIN;

DO $$
DECLARE
    stamp text := to_char(now() AT TIME ZONE 'UTC', 'YYYYMMDD_HH24MISS');
BEGIN
    IF to_regclass('public.marketing_consent_events') IS NOT NULL THEN
        EXECUTE format('CREATE TABLE %I AS TABLE marketing_consent_events', 'marketing_consent_events_bak_058_' || stamp);
    END IF;
    IF to_regclass('public.email_suppressions') IS NOT NULL THEN
        EXECUTE format('CREATE TABLE %I AS TABLE email_suppressions', 'email_suppressions_bak_058_' || stamp);
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketing_leads' AND column_name = 'reminder_sent_at'
    ) THEN
        EXECUTE format(
            'CREATE TABLE %I AS SELECT id, email, reminder_sent_at, a1_sent_at, l1m_sent_at, minor_reclass_at FROM marketing_leads',
            'marketing_leads_bak_058_' || stamp
        );
    END IF;
END $$;

DROP TABLE IF EXISTS email_suppressions;
DROP TABLE IF EXISTS marketing_consent_events;

ALTER TABLE marketing_leads
    DROP COLUMN IF EXISTS minor_reclass_at,
    DROP COLUMN IF EXISTS l1m_sent_at,
    DROP COLUMN IF EXISTS a1_sent_at,
    DROP COLUMN IF EXISTS reminder_sent_at;

-- Let the migrator re-apply 058 on the next deploy.
DELETE FROM schema_migrations WHERE filename = '058_marketing_consent_events.sql';

COMMIT;
