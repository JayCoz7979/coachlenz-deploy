# Tenant Isolation: RLS Backstop Plan

Defense-in-depth plan for a database-level Row Level Security (RLS) backstop under
the existing app-layer tenant isolation. Written 2026-07-30. Facts below were
verified directly against the production Postgres, not assumed.

## Current state (verified 2026-07-30)

- Tenant isolation today is **app-layer only**: every query filters by
  `organization_id`, and every by-id endpoint 404s cross-org. This is audited
  consistent and now **regression-guarded** by the cross-org sweep in
  `backend/tests/test_api_integration.py` (`cross_org_isolation`).
- **No RLS is enabled** on any table (`games`, `events`, `tendency_reports`,
  `jobs`, `users`, `organizations` all `relrowsecurity=false`).
- The application connects as role **`postgres`**, which is `rolsuper=true` and
  `rolbypassrls=true`. **A superuser bypasses RLS entirely — even `FORCE ROW
  LEVEL SECURITY` does not apply to a superuser.**
- There is **no non-superuser application login role**. The only login role is
  `postgres`; every other role is a built-in `pg_*` system role.

## Why RLS is not a drop-in

Because the app connects as a superuser, simply enabling RLS + policies would be
**inert** — switched on but bypassed by every connection, giving a false sense of
protection. Making RLS a real backstop requires four coordinated changes.
Shipping any one alone is either inert or an outage:

1. A dedicated **`NOSUPERUSER NOBYPASSRLS`** login role with DML + sequence grants
   on the tenant tables.
2. Repointing `DATABASE_URL` on **all 9 Railway services** to that role.
3. A **per-request GUC** (`SET LOCAL app.org_id = <org>`) set after auth resolves
   the org, which RLS policies read via `current_setting('app.org_id', true)`.
4. A **worker DB-access refactor**. The workers (ingest, reports, analysis, drip,
   referrals, survey, packages, ...) are **cross-org by design** — they process
   jobs for any org. Under RLS, a worker connecting as the restricted role with no
   `app.org_id` set sees **zero rows** and breaks. Each worker must set
   `app.org_id` per job, or hold a separate privileged connection for queue polling
   and set the GUC before touching tenant data.

## Blast radius

All 9 services share the database. A wrong policy or a missing GUC on any code
path returns **0 rows for every query on that path** — a silent, total outage that
looks like "all data disappeared." This is why RLS is never shipped prod-first and
never via an auto-applied migration alone.

## Staged rollout (each stage reversible; validate on a Railway DB branch first)

- **Stage 0 — SHIPPED (PR #106).** Cross-org regression sweep locks the app-layer
  guarantee so any future code change that breaks isolation fails CI.
- **Stage 1 — SHIPPED.** Role `app_rls` (`NOLOGIN NOSUPERUSER NOBYPASSRLS`) + DML
  grants + default privileges, via the **additive, inert** migration
  `031_rls_app_role.sql` (no login, no RLS yet). Verified idempotent and prod-safe
  by applying it inside a rolled-back transaction. Safe to auto-apply.
- **Stage 2.** Add the GUC layer: set `app.org_id` in the request-scoped
  `get_db` path once auth resolves the org, plus a `set_org_context(org_id)` helper
  for workers. Still no RLS. Assert/log in staging that `app.org_id` is set on every
  request and every worker job before any tenant query.
- **Stage 3.** On a **staging / DB-branch** only: `ENABLE` + `FORCE` RLS + policies
  on every tenant table. Run the full test suite AND a manual cross-org probe while
  connected as `app_rls`. This is where 0-rows bugs surface — fix them here, never
  in prod.
- **Stage 4.** Cut over **one low-risk service's** `DATABASE_URL` to `app_rls` in
  prod, watch logs/health, then roll the rest one at a time. Keep env-revert as an
  instant rollback.

## Mechanism proof (backend/tests/rls_poc.py, run 2026-07-30)

RLS is a Postgres feature; CI runs on SQLite and cannot test it. `rls_poc.py`
proves the mechanism against the real production Postgres, in a throwaway schema
with a real `NOSUPERUSER` role, cleaning up after itself (touches no app tables).
All six checks pass:

1. A superuser connection **bypasses** RLS (sees all rows) — this is why prod is
   inert until the `DATABASE_URL` cutover.
2. Restricted role, **no** `app.org_id` set → **0 rows** (fail-closed).
3. `app.org_id` = org A → only org A's rows.
4. `app.org_id` = org B → only org B's rows.
5. A cross-org `INSERT` is **rejected** by the policy `WITH CHECK` (SQLSTATE
   42501, reported as insufficient-privilege).
6. A same-org `INSERT` is allowed.

**Tenant-table inventory:** 27 tables carry `organization_id` and will need a
policy in Stage 3: agent_logs, analysis_usage, audit_logs, clip_assignments,
clips, coach_moves, coach_profiles, coach_usage_limits, device_fingerprints,
events, film_packages, games, grade_annotations, jobs, messages, notifications,
playlists, referral_codes, risk_flags, roster_players, source_connections,
survey_responses, tags, teams, tendency_reports, threads, users.

## Policy shape (reference)

```sql
ALTER TABLE games ENABLE ROW LEVEL SECURITY;
ALTER TABLE games FORCE  ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON games
  USING (organization_id = current_setting('app.org_id', true)::uuid)
  WITH CHECK (organization_id = current_setting('app.org_id', true)::uuid);
-- repeat for every tenant table: events, tendency_reports, jobs, clips,
-- agent_logs, teams, and any table carrying organization_id.
```

`current_setting('app.org_id', true)` returns NULL when unset (the `true` =
missing_ok), so an unset context matches no rows — fail-closed, which is correct,
and exactly why Stage 2's "GUC is always set" verification must precede Stage 3.
