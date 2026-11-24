-- Reverse of 060_legal_acceptance_user_agent.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/060_legal_acceptance_user_agent.down.sql
--
-- Drops signup User-Agent evidence. It is first copied, with the row id, to
-- legal_acceptances_ua_bak_060_<UTC timestamp>. One transaction.

BEGIN;

DO $$
DECLARE
    stamp text := to_char(now() AT TIME ZONE 'UTC', 'YYYYMMDD_HH24MISS');
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'legal_acceptances' AND column_name = 'user_agent'
    ) THEN
        EXECUTE format(
            'CREATE TABLE %I AS SELECT id, user_agent FROM legal_acceptances WHERE user_agent IS NOT NULL',
            'legal_acceptances_ua_bak_060_' || stamp
        );
    END IF;
END $$;

ALTER TABLE legal_acceptances
    DROP COLUMN IF EXISTS user_agent;

-- Let the migrator re-apply 060 on the next deploy.
DELETE FROM schema_migrations WHERE filename = '060_legal_acceptance_user_agent.sql';

COMMIT;
