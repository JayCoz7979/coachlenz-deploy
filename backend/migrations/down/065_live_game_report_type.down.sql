-- 065 down: restore the pre-065 report_type check. Run by hand only.
-- The migration runner globs backend/migrations/*.sql and never enters this folder.
-- Refuses while any live_game row exists, so a rollback cannot strand or reject
-- reports coaches already generated. The RAISE aborts this transaction, so the
-- constraint and schema_migrations row stay as they were. Safe to run twice
-- once no live_game rows remain (the DELETE matches zero rows the second time).

BEGIN;

DO $$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n FROM tendency_reports WHERE report_type = 'live_game';
    IF n > 0 THEN
        RAISE EXCEPTION '065 down refused: % live_game report row(s) exist. Nothing was changed.', n;
    END IF;
END $$;

ALTER TABLE tendency_reports
    DROP CONSTRAINT IF EXISTS tendency_reports_report_type_check;

ALTER TABLE tendency_reports
    ADD CONSTRAINT tendency_reports_report_type_check
    CHECK (report_type IN ('opponent', 'self_scout', 'custom'));

DELETE FROM schema_migrations WHERE filename = '065_live_game_report_type.sql';

COMMIT;
