-- RLS Backstop — Stage 4 pre-cutover grant refresh. Idempotent.
--
-- Belt-and-suspenders over migration 031's ALTER DEFAULT PRIVILEGES: guarantees the
-- app_rls role can access EVERY current table + sequence before the cutover, so the
-- backend (once connected as app_rls) never hits a "permission denied" on a table that
-- slipped through default privileges. RLS still scopes the ROWS per org; this only
-- grants table-level DML. Safe to run any number of times.

GRANT USAGE ON SCHEMA public TO app_rls;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rls;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rls;

-- Re-assert the default privileges too (covers tables created by future migrations).
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rls;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_rls;
