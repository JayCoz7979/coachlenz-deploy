-- Reverse of 056_games_r2_key_unique.sql. The migrator ignores *.down.sql.
-- Run this by hand only when rolling the schema back:
--   psql "$DATABASE_URL" -f backend/migrations/056_games_r2_key_unique.down.sql
DROP INDEX IF EXISTS games_r2_key_unique;
