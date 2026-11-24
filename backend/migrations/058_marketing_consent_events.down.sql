-- Reverse of 058_marketing_consent_events.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -f backend/migrations/058_marketing_consent_events.down.sql

DROP TABLE IF EXISTS email_suppressions;
DROP TABLE IF EXISTS marketing_consent_events;

ALTER TABLE marketing_leads
    DROP COLUMN IF EXISTS minor_reclass_at,
    DROP COLUMN IF EXISTS l1m_sent_at,
    DROP COLUMN IF EXISTS a1_sent_at,
    DROP COLUMN IF EXISTS reminder_sent_at;
