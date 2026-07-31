-- RLS backstop, Stage 1 of 4. See docs/security/rls-backstop-plan.md.
--
-- Creates the dedicated NOSUPERUSER application role that RLS will later be
-- enforced against, and grants it DML on the public schema.
--
-- This migration is INERT and safe to auto-apply on prod: the role is NOLOGIN
-- (nothing can connect as it yet) and NO row-level security is enabled by this
-- file, so it changes zero runtime behavior. The app keeps connecting as the
-- `postgres` superuser, which bypasses RLS entirely (verified in
-- backend/tests/rls_poc.py).
--
-- Later stages (separate, staging-validated PRs): the per-request `app.org_id`
-- session GUC, ENABLE + FORCE RLS + policies on the 27 tenant tables, then the
-- DATABASE_URL cutover from `postgres` to `app_rls` one service at a time.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rls') THEN
    CREATE ROLE app_rls NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;

-- DML on today's tables. RLS (a later stage) is what will scope these per-org;
-- the grant itself is intentionally broad and harmless while the role is unused.
GRANT USAGE ON SCHEMA public TO app_rls;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rls;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rls;

-- Future tables/sequences created by the migration role inherit the same grants,
-- so a new table added before the cutover is not silently inaccessible to the app.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rls;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_rls;
