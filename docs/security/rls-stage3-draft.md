# RLS Backstop — Stage 3 (DRAFT, review-only)

**Status: DRAFT. Do NOT enable on production. Do NOT merge as "live."** This prepares
Stage 3 of `rls-backstop-plan.md` for validation on a Railway Postgres DB-branch. The
code here is DORMANT (gated off), and the SQL is deliberately kept out of
`backend/migrations/` so the deploy migration runner cannot auto-apply it. Nothing in
this draft changes prod behavior until it is validated on a branch and explicitly
turned on.

Why the gate matters (from the plan): all 9 services share one database. A wrong
policy or a single unscoped code path returns **0 rows for every query on that path**
— a silent, total outage that looks like "all data disappeared." That is why RLS is
validated on a branch (connected as `app_rls`) before any prod cutover, never
prod-first, never via an auto-applied migration.

## Current state (verified 2026-08-01, in code)

- Stage 0 (done, #106): cross-org regression sweep in `test_api_integration.py`.
- Stage 1 (done): role `app_rls` (`NOLOGIN NOSUPERUSER NOBYPASSRLS`), migration 031.
- Stage 2 (done, dormant): `models/rls.py` ContextVar + `after_begin` GUC listener
  stamping `app.org_id` per transaction, gated on `RLS_ENABLED` (off); set from the
  JWT in `auth.py`.
- Mechanism proven: `rls_poc.py` 6/6 against real Postgres (2026-07-30).

## What this draft adds

- `backend/scripts/rls/stage3_enable_rls.sql` — ENABLE + FORCE RLS + `org_isolation`
  policy on **every** table carrying `organization_id`, driven dynamically off
  `information_schema` (so it can never miss a table). Fail-closed via
  `NULLIF(current_setting('app.org_id', true), '')::uuid`. Applied by hand on the
  DB-branch. `stage3_disable_rls.sql` reverses it (instant rollback).
- `backend/models/rls_engine.py` — dual-engine scaffolding + `get_db_restricted` /
  `get_db_privileged` dependencies. Dormant until `RLS_ENABLED` AND
  `DATABASE_URL_RESTRICTED` are both set.
- `config.DATABASE_URL_RESTRICTED` — the `app_rls` DSN (empty by default).

## Org-scoped table inventory (32 as of 2026-08-01, up from 27 in the plan)

The 5 added since the plan — and exactly why the policy script is dynamic, not a
hardcoded list: `account_learning_adjustments`, `coach_label_corrections`,
`label_quality_scores`, `legal_acceptances`, `report_chat_messages`.

Full set: account_learning_adjustments, agent_logs, analysis_usage, audit_logs,
clip_assignments, clips, coach_label_corrections, coach_moves, coach_profiles,
coach_usage_limits, device_fingerprints, events, film_packages, games,
grade_annotations, jobs, label_quality_scores, legal_acceptances, messages,
notifications, playlists, referral_codes, report_chat_messages, risk_flags,
roster_players, source_connections, survey_responses, tags, teams, tendency_reports,
threads, users.

(`processed_stripe_events` has no `organization_id` — it is global Stripe-event dedup,
correctly NOT covered.)

## Privileged paths (must use `get_db_privileged`, NOT the restricted engine)

These are legitimately cross-org and would fail-closed to 0 rows under RLS:

1. **Auth bootstrap** (`routers/auth.py`): login, refresh, register/signup, forgot-
   password + reset. No org is known yet, so they cannot be org-scoped.
2. **Public share link** (`routers/reports.py` `GET /reports/{id}/share/{token}`):
   reads a report across orgs by capability token.
3. **Workers** (all `backend/workers/*`): the job-queue poll (`SELECT next job`) is
   cross-org. Each worker must `set_org_context(job.organization_id)` after claiming a
   job and BEFORE touching tenant data, then `reset_org_context()` after. (This is the
   Stage-2-deferred worker wiring; it lands here.)

Everything else — every authenticated request handler that runs under
`get_current_user` — uses `get_db_restricted`. `get_current_user` already
`set_org_context(jwt.org)` before its first query, so the users lookup is itself
org-scoped and returns the caller's own user (no bootstrap deadlock).

## Validation runbook (DB-branch only)

1. **Create a Railway Postgres DB-branch** from prod (a throwaway copy of the schema).
2. **Create the login role** on the branch: `ALTER ROLE app_rls LOGIN PASSWORD '<pw>';`
   (Stage 1 created it NOLOGIN.) Confirm it is `NOSUPERUSER NOBYPASSRLS`.
3. **Apply the policies:** run `backend/scripts/rls/stage3_enable_rls.sql` on the branch
   (as the migration/superuser role).
4. **Point the app at the branch as `app_rls`:** set `DATABASE_URL` (or per-service) to
   the branch, `DATABASE_URL_RESTRICTED` to the `app_rls` DSN, and `RLS_ENABLED=true`.
5. **Wire the dependencies** (this is the real work, done here where bugs are safe):
   - org-scoped routers: `Depends(get_db)` -> `Depends(get_db_restricted)`.
   - bootstrap + share-link routes: `-> get_db_privileged`.
   - workers: `set_org_context(job.organization_id)` per job on the privileged engine.
6. **Run the full test suite** against the branch, then a **manual cross-org probe**
   while connected as `app_rls`: confirm org A cannot see org B on every surface, and
   that login / share links / a real ingest+report job all still return rows.
7. **Fix every 0-rows breakage here.** This is the stage where they surface. Re-run.
8. Only once green: proceed to **Stage 4** — cut over ONE low-risk service's
   `DATABASE_URL` to `app_rls` in prod, watch logs/health, then roll the rest one at a
   time. Keep an env-revert (`RLS_ENABLED=false` or DSN back to `postgres`) as an
   instant rollback.

## Rollback

- On the branch: `stage3_disable_rls.sql`, or `RLS_ENABLED=false`.
- In prod (Stage 4): revert the service's `DATABASE_URL` env to `postgres` (the
  superuser bypasses RLS, restoring the pre-cutover behavior instantly).

## What this draft does NOT do

- It does not wire the routers/workers to the new dependencies (that is step 5, done
  during validation so the 0-rows bugs surface where they are cheap to fix).
- It does not enable RLS anywhere. The SQL is manual + branch-only; the code is dormant.
