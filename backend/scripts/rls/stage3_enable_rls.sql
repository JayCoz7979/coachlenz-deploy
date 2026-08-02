-- RLS Backstop — Stage 3 policy enable. Applied BY HAND (never auto-applied).
--
-- Validation phase: run on an isolated DB / DB-branch only.
-- Stage 4 (production): this IS a step of docs/security/rls-stage4-cutover.md. It is
-- SAFE to run on prod BEFORE the cutover and stays INERT there: every service still
-- connects as the `postgres` superuser, which bypasses RLS even under FORCE, so no row
-- is hidden until a service's DATABASE_URL_RESTRICTED + RLS_ENABLED flip it onto the
-- app_rls role. Do NOT run it expecting immediate enforcement — enforcement begins at
-- the env flip, not here.
--
-- Enables + FORCES Row Level Security with an org-isolation policy on every table
-- that carries an organization_id column. Driven dynamically off information_schema
-- so it covers all current AND future org-scoped tables (32 as of 2026-08-01) — a
-- hardcoded list would silently miss tables added later (it already would have missed
-- the 5 learning/legal/report-chat tables added after the original plan).
--
-- FAIL-CLOSED: Stage 2's GUC listener stamps app.org_id = '' when there is no org
-- context. NULLIF('', ...) -> NULL, and (organization_id = NULL) is NULL (never true),
-- so an unscoped connection sees ZERO rows on every table. That is the desired safe
-- default, and it is also exactly why every legitimately-cross-org path (auth
-- bootstrap, public share links, worker queue poll) MUST use the privileged engine
-- or set app.org_id explicitly — see docs/security/rls-stage3-draft.md.
--
-- Idempotent (DROP POLICY IF EXISTS). Reverse with stage3_disable_rls.sql.
--
-- WHY NOT A MIGRATION: backend/migrate.py auto-applies backend/migrations/*.sql on
-- every deploy. RLS enablement must never auto-apply — it is validated on a DB-branch
-- (connected as app_rls) first, because a wrong policy or an unscoped path is a silent
-- 0-rows outage across all 9 services. So this lives under scripts/ and is applied by
-- hand on the branch only.

DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT table_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND column_name = 'organization_id'
    ORDER BY table_name
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE  ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS org_isolation ON public.%I', t);
    EXECUTE format($ddl$
      CREATE POLICY org_isolation ON public.%I
        USING      (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
    $ddl$, t);
    RAISE NOTICE 'RLS org_isolation applied to %', t;
  END LOOP;
END $$;
