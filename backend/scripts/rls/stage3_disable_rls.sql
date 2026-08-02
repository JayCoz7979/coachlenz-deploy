-- RLS Backstop — Stage 3 rollback (DRAFT). DB-BRANCH ONLY.
--
-- Reverses stage3_enable_rls.sql: drops the org_isolation policy and turns RLS off on
-- every org-scoped table. Instant rollback if the DB-branch validation surfaces a
-- 0-rows bug. Idempotent.

DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT table_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND column_name = 'organization_id'
    ORDER BY table_name
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS org_isolation ON public.%I', t);
    EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I DISABLE  ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
