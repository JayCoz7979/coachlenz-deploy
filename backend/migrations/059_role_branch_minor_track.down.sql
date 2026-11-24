-- Reverse of 059_role_branch_minor_track.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -f backend/migrations/059_role_branch_minor_track.down.sql
-- Safe to run twice, and safe after 057's down has already dropped role_branch:
-- the rename only runs while the column exists.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketing_leads' AND column_name = 'role_branch'
    ) THEN
        UPDATE marketing_leads
            SET role_branch = 'player_hold'
            WHERE role_branch = 'minor_track';
    ELSE
        RAISE NOTICE '059 down: marketing_leads.role_branch is gone, nothing to rename';
    END IF;
END
$$;

-- Let the migrator re-apply 059 on the next deploy.
DELETE FROM schema_migrations WHERE filename = '059_role_branch_minor_track.sql';

COMMIT;
