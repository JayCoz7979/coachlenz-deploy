-- Reverse of 059_role_branch_minor_track.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -f backend/migrations/059_role_branch_minor_track.down.sql

UPDATE marketing_leads
    SET role_branch = 'player_hold'
    WHERE role_branch = 'minor_track';
