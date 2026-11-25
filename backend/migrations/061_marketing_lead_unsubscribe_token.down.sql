-- Reverse of 061_marketing_lead_unsubscribe_token.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/061_marketing_lead_unsubscribe_token.down.sql
--
-- WARNING: puts back the old (null or blank) token on the rows 061 filled, but
-- only where the token is still the one 061 wrote. Any email sent with those
-- tokens after 061 will then carry a link that unsubscribes nobody. Drops the
-- unique index. One transaction, and safe to run twice (or after 057's down).

BEGIN;

-- Drop the unique index before any restore. Two leads that 061 filled from a
-- blank token both go back to '', and two reissued duplicates go back to the
-- same shared token. Either restore hits the unique index if it is still there.
DROP INDEX IF EXISTS marketing_leads_unsubscribe_token_key;

DO $$
BEGIN
    IF to_regclass('public.marketing_leads_token_backfill_061') IS NULL THEN
        RAISE NOTICE '061 down: no backfill record, nothing to undo';
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketing_leads' AND column_name = 'unsubscribe_token'
    ) THEN
        RAISE NOTICE '061 down: marketing_leads.unsubscribe_token is gone, nothing to undo';
        DROP TABLE marketing_leads_token_backfill_061;
    ELSE
        UPDATE marketing_leads AS m
            SET unsubscribe_token = b.old_token
            FROM marketing_leads_token_backfill_061 AS b
            WHERE m.id = b.lead_id AND m.unsubscribe_token = b.new_token;
        DROP TABLE marketing_leads_token_backfill_061;
    END IF;
END
$$;

-- Let the migrator re-apply 061 on the next deploy.
DELETE FROM schema_migrations WHERE filename = '061_marketing_lead_unsubscribe_token.sql';

COMMIT;
