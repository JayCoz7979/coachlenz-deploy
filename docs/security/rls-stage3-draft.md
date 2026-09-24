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

WIRED 2026-08-01. Rather than edit every org-scoped router, `models/base.get_db` now
routes to the **restricted** engine by default (secure-by-default: a handler that
forgets its `organization_id` filter still can't leak), and only the genuinely
cross-org paths below are overridden back to `get_db_privileged`. This set was found
by an AST audit of every router (`get_db` present, no auth dependency that chains to
`get_current_user`), NOT by guesswork. The full set (larger than the original draft —
the audit added the admin router and two more public-token readers):

1. **Auth bootstrap** (`routers/auth.py`): register, login, refresh, forgot-password,
   reset-password. No org is known yet, so they cannot be org-scoped. (register also
   writes the org-scoped `legal_acceptances` before any JWT exists — only works on the
   privileged engine.) `logout` / `change-password` / `verify-*` stay restricted: they
   run under `get_current_user`, which sets the org context.
2. **Public capability-token readers** (no login, scoped by an unguessable token, read
   an org-scoped table cross-org): `reports.py GET /{id}/share/{token}`,
   `recruiting.py GET /share/{token}`, `packages.py GET /view/{token}`.
3. **Stripe webhook** (`billing.py POST /webhook`): no logged-in org; looks up the org
   by Stripe customer/metadata and writes org-scoped rows for whichever org the event
   names.
4. **Admin** (all of `routers/admin.py`, via an aliased import): authenticated as the
   admin's own org but queries **across** orgs (list/patch/delete every org, platform
   stats, cross-tenant risk flags). Under the restricted engine RLS would silently
   clamp it to the admin's own org. Still gated by `require_admin`.

Everything else — every authenticated request handler under `get_current_user`,
`get_current_org`, `require_role`/`require_permission`, `require_admin` (which itself
chains to `get_current_user`), etc. — uses the restricted engine via the default
`get_db`. `get_current_user` already `set_org_context(jwt.org)` before its first
query, so the users lookup is itself org-scoped and returns the caller's own user (no
bootstrap deadlock).

**Workers** (`backend/workers/*`): unchanged — they open sessions via
`AsyncSessionLocal` (the **privileged** engine) directly, so the cross-org job-queue
poll bypasses RLS and sees every org's jobs (correct). Per-job
`set_org_context(job.organization_id)` is defense-in-depth for a *future* move of
workers onto the restricted engine; it is NOT required for correctness while workers
run on the privileged engine, and is deliberately deferred to keep this slice tight.

## Validation status (2026-08-01)

The **SQL / policy half is validated** against the real schema, in isolation, with no
prod app table touched:

- **Policy mechanism** (throwaway schema on the real Postgres, cleaned up) — 6/6:
  `app.org_id=''` (Stage 2's fail-closed value) returns 0 rows and does NOT error on
  `''::uuid` (this is the `NULLIF` fix); unset context -> 0 rows; org A -> A only;
  org B -> B only; cross-org INSERT rejected by `WITH CHECK`; same-org INSERT allowed.
- **Coverage on the full real schema** (stood up an isolated `rls_stage3_val` database,
  applied all 36 migrations -> 47 tables, then `stage3_enable_rls.sql`, then dropped it):
  all **32** org-scoped tables got ENABLE+FORCE RLS + the `org_isolation` policy; the
  15 non-org tables (incl. `processed_stripe_events`) got none; zero missing, zero
  over-reach. The dynamic script applies cleanly to every real table.

**The app-code half is now WIRED and the core path is VALIDATED (2026-08-01).** The
router wiring above is in place (default-restricted `get_db` + the privileged
overrides). Proven by booting the REAL FastAPI app against an isolated `rls_stage3_val`
database (all 36 migrations + `stage3_enable_rls.sql`), privileged engine as
`postgres`, restricted engine as an ephemeral `app_rls_val` login role
(`NOSUPERUSER NOBYPASSRLS`, dropped after — the shared prod `app_rls` role is NEVER
given a login password), `RLS_ENABLED=true`, driving real HTTP — `rls_app_validate.py`,
**11/11 PASS**:

- dual engine active + restricted engine distinct from privileged;
- `register` (both orgs) + `login` succeed on the privileged engine (bootstrap writes
  org + user + `legal_acceptances` with no org context yet, and the user lookup is not
  fail-closed);
- `GET /games` **returns the caller's row** on the restricted engine (the key proof it
  is not fail-closed to 0) and does **not** leak the other org's row;
- `GET /games/{own}` → 200, `GET /games/{other-org}` → 404 (cross-org isolation);
- direct `app_rls_val` connection: no context → 0 rows (RLS genuinely enforcing at the
  DB level, independent of the app-layer filter); `app.org_id=A` → exactly A's rows.

**Slice 2 — broader path coverage VALIDATED (2026-08-01), now 16/16 in
`rls_app_validate.py`.** Added end-to-end checks for every remaining path TYPE:

- **Share link:** `POST /reports/{id}/share` mints the token on the RESTRICTED engine
  (finds the caller's report), and the public `GET /reports/{id}/share/{token}` returns
  it on the PRIVILEGED engine with no org context — both halves work.
- **Admin (cross-org):** a platform admin's `GET /admin/orgs` sees BOTH orgs via the
  privileged alias; the same surface 404s for a non-admin org. Proves the admin router
  is not clamped to its own org, and the gate still holds.
- **Worker poll:** a query on `AsyncSessionLocal` (the exact engine workers use) with no
  org context sees BOTH orgs' jobs — the cross-org queue poll is not fail-closed.

**Privileged-engine audit (completeness, 2026-08-01):** grepped every request-path use
of the privileged engine (`AsyncSessionLocal` / `engine.connect` outside workers, tests,
bootstrap). The ONLY hits are non-tenant or write-only: `health.py` (`SELECT 1`),
`teams_of_month.py GET /featured` (the global `featured_teams` table, no
`organization_id`), and `services/agent_log.py` (UATP logger — writes `agent_logs` on a
separate privileged session with an explicit `organization_id`, correct for an audit
log, never reads cross-org). So no request handler silently bypasses RLS to read/leak
tenant data.

**Deferred to Stage 4 staging (deliberate, not skipped):** re-pointing the SQLite unit
harness (`test_api_integration.py`) at Postgres-as-`app_rls`. That harness hard-binds
SQLite at import, swaps UUID/JSONB/ARRAY to SQLite shims, and builds schema via
`create_all` (not migrations) — re-pointing it is a large fork that "fights the
module-level engine" (see the tenant-isolation memory), and it would mostly re-exercise
the same authenticated→restricted category already proven representative here. The
natural place for a full-suite run under RLS is the Stage-4 Railway DB-branch (real
Postgres), where SQLite isn't in the way — not a fork of the unit harness. The core
request path, every privileged path, the worker poll, and the DB-level mechanism are
all proven on real Postgres with RLS forced.

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

- It does not enable RLS anywhere in prod. The SQL is manual + isolated-DB-only, and
  the wiring is DORMANT: with `RLS_ENABLED=false` (prod default) and
  `DATABASE_URL_RESTRICTED=""`, `RestrictedSessionLocal` and `get_db_privileged` both
  resolve to the existing privileged `AsyncSessionLocal`, so `get_db`, every privileged
  override, and the admin alias all use the exact same engine as before — a
  byte-for-byte no-op in prod and CI. Verified: the app imports and all edited routers
  load cleanly; prod behavior is unchanged until Stage 4 flips the flag + DSN.
- The router wiring IS now in place (previously deferred). Worker per-job
  `set_org_context` is still deferred (workers run on the privileged engine, which is
  correct as-is — see the privileged-paths section).
