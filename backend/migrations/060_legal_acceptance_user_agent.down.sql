-- Reverse of 060_legal_acceptance_user_agent.sql. Not applied by the migrator.
--   psql "$DATABASE_URL" -f backend/migrations/060_legal_acceptance_user_agent.down.sql

ALTER TABLE legal_acceptances
    DROP COLUMN IF EXISTS user_agent;
