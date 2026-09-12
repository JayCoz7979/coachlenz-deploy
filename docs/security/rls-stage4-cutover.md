# RLS Backstop — Stage 4 Production Cutover Checklist

The exact, ordered steps to turn the RLS backstop ON in production. Stages 0–3 are
done and validated (see `rls-stage3-draft.md`, 16/16 on real Postgres). This is the
only stage that changes prod behavior. Read the whole thing once before running any of
it. Every step is reversible; the rollback is a single env var.

## What Stage 4 actually does (and does NOT do)

The design is **dual-engine**, so the cutover is NOT the "swap `DATABASE_URL` to
app_rls" the original plan imagined:

- `DATABASE_URL` stays exactly as it is (the `postgres` superuser). It backs the
  **privileged** engine used by auth bootstrap, public share links, the Stripe webhook,
  the admin router, and **all workers**. Those keep working unchanged.
- You **add** `DATABASE_URL_RESTRICTED` (the `app_rls` role) and set `RLS_ENABLED=true`.
  That activates the **restricted** engine, which every ordinary org-scoped HTTP handler
  now uses, so Postgres RLS enforces org isolation on those queries.

Only **one service** serves org-scoped HTTP handlers: **`coachlenz-backend`**
(`WORKERS_IN_API=light`, so no workers run in it). The 7 worker services and the
frontend are NOT touched. So the "one service at a time" rollout is really "flip
`coachlenz-backend`, watch, done" — with an instant env revert if anything goes wrong.

**Blast radius:** a wrong policy or an unscoped handler returns 0 rows for that path — a
silent outage that looks like "data disappeared." That is why RLS is enabled on the
tables first (inert, because the superuser bypasses it) and enforcement is turned on by
an env flip that can be reverted in seconds.

## Prerequisites (do these once, before the window)

- **P1. Merge the draft.** PR #148 (the wiring + scripts) must be on `main` and deployed
  to `coachlenz-backend`. It is dormant (`RLS_ENABLED=false`, no `DATABASE_URL_RESTRICTED`)
  so deploying it changes nothing until you flip the env in Step 5.
- **P2. Know your database.** Confirm `coachlenz-backend`'s `DATABASE_URL` points at the
  `Postgres` service (db `railway`), the same one these scripts target. In the Railway
  dashboard: `coachlenz-backend` → Variables → `DATABASE_URL` should reference
  `${{Postgres.*}}`. All commands below run against that DB.

All SQL below is applied with the repo helper (no `psql` needed). `railway run --service
Postgres` injects that DB's credentials; the helper prints the database + role it is
about to touch before doing anything.

---

## Step 0 — Pre-flight readiness check (read-only, safe anytime)

```bash
railway run --service Postgres -- python backend/scripts/rls/verify_rls_prod.py
```

Expect: app_rls exists, `superuser=False`, `bypassrls=False`; coverage line will show
0 policies so far; grant gaps `none` (or a short list you'll fix in Step 2); RLS not
enabled yet. If app_rls is missing, migration 031 hasn't run — deploy P1 first.

## Step 1 — Give app_rls a login password (out-of-band, YOU do this)

The `app_rls` role is `NOLOGIN` today (migration 031). It must never get a login
password in a migration or in git — it has DML on the tenant tables, and while RLS is
off a login there could read everything. Set it by hand, once, with a strong secret:

```bash
railway run --service Postgres -- python backend/scripts/rls/apply_sql.py /dev/stdin <<'SQL'
ALTER ROLE app_rls LOGIN PASSWORD 'PUT-A-STRONG-SECRET-HERE';
SQL
```

(or run the single `ALTER ROLE` in any superuser SQL console). Use a long random
secret. Keep it only in Railway (Step 4), not in the repo. Re-run Step 0 — `canlogin`
should now be `True`.

## Step 2 — Refresh app_rls grants (idempotent, safe)

Guarantees app_rls can reach every current table, closing any gap in migration 031's
default privileges before the cutover:

```bash
railway run --service Postgres -- python backend/scripts/rls/apply_sql.py backend/scripts/rls/grant_app_rls.sql
```

Re-run Step 0 and confirm **grant gaps: none**. Do not proceed until it says none.

## Step 3 — Enable RLS on the tables (INERT — superuser still bypasses)

This adds ENABLE + FORCE + the `org_isolation` policy to all org-scoped tables. It is
**inert** the moment it runs, because every service is still connected as `postgres`
(superuser bypasses RLS even under FORCE). Nothing changes for users yet.

```bash
railway run --service Postgres -- python backend/scripts/rls/apply_sql.py backend/scripts/rls/stage3_enable_rls.sql
```

Then verify:

```bash
railway run --service Postgres -- python backend/scripts/rls/verify_rls_prod.py
```

Expect: coverage now shows **all org-scoped tables** with the policy + FORCE; step 4 of
the output says RLS is enabled but **INERT until a service connects as app_rls**. Confirm
the app is still healthy (it is — nothing enforces yet):

```bash
curl -s https://coachlenz-backend-production.up.railway.app/health
```

**If you stop here, prod is exactly as before.** Steps 0–3 are the safe, reversible
groundwork; Step 5 is the only behavioral change.

## Step 4 — Set the restricted DSN on coachlenz-backend (do NOT flip RLS yet)

Set `DATABASE_URL_RESTRICTED` to the app_rls DSN, built from the same Postgres the
backend already uses, over the private network. In the Railway dashboard for
**coachlenz-backend** → Variables, add (raw editor):

```
DATABASE_URL_RESTRICTED=postgresql+asyncpg://app_rls:PUT-A-STRONG-SECRET-HERE@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

- Use the SAME password from Step 1.
- Keep the `postgresql+asyncpg://` scheme (the app uses asyncpg).
- Do NOT set `RLS_ENABLED` yet. With `RLS_ENABLED` still false, the dual-engine stays
  dormant (`_RLS_ACTIVE` needs BOTH), so this deploy is still a no-op. This step just
  proves the DSN is accepted and the service boots.

Let it redeploy, then `curl .../health` again — still green.

**Do NOT set `DATABASE_URL_RESTRICTED` on any worker service.** Workers must stay on the
privileged engine.

## Step 5 — Flip enforcement ON (the cutover)

Set the flag on **coachlenz-backend only**:

```bash
railway variables --set "RLS_ENABLED=true" --service coachlenz-backend
```

(or toggle it in the dashboard). Railway redeploys the service. At boot, org-scoped
handlers switch to the app_rls engine and RLS begins enforcing. Bootstrap, admin, share
links, the webhook, and all workers stay on the privileged engine.

## Step 6 — Watch (first 5–10 minutes, keep this window open)

Watch the logs live:

```bash
railway logs --service coachlenz-backend
```

Run a real smoke test against prod (use a throwaway test coach account, or your own):

1. `POST /auth/login` → 200 + token (privileged path).
2. `GET /games` with that token → returns that org's games, **not empty** if the org has
   film. **Empty when it should not be is the #1 red flag** (a handler fail-closing).
3. Open a game, a report, the roster in the app UI — data should render as before.
4. Generate or open a share link → the public page loads (privileged path).

**Red flags → roll back immediately (Step 7):**
- Endpoints that used to return data now return `[]` / 404 / "not found."
- `permission denied for table ...` in logs (a grant gap — Step 2 missed something).
- `InsufficientPrivilege` / policy errors, or a spike in 5xx.

**Healthy signs:** data renders as before, no permission errors, workers still draining
jobs (`railway logs --service coachlenz-worker_ingest`).

## Step 7 — Rollback (instant, if anything looks wrong)

Fastest — revert the flag; the backend goes back to the privileged engine everywhere:

```bash
railway variables --set "RLS_ENABLED=false" --service coachlenz-backend
```

That is the whole rollback: superuser bypass is restored, all rows visible again, in one
redeploy. (The RLS policies stay on the tables but are inert again.) You can leave
`DATABASE_URL_RESTRICTED` set; it's dormant without the flag.

If you also want to remove the policies entirely (e.g. abandoning the effort):

```bash
railway run --service Postgres -- python backend/scripts/rls/apply_sql.py backend/scripts/rls/stage3_disable_rls.sql
```

## Step 8 — Confirm isolation is actually enforcing (after a clean cutover)

Prove RLS is live, not just inert, with the read-only checks:

```bash
railway run --service Postgres -- python backend/scripts/rls/verify_rls_prod.py
```

For a live cross-org proof against prod, use the same technique the validation harness
used (a direct app_rls connection with no `app.org_id` returns 0 rows; with a real org
id returns only that org). Run it as a one-off; do not leave the app_rls password
lying around in shell history.

## Notes / decisions baked in

- **Why not cut a worker service first as the "low-risk canary"?** Workers don't use the
  restricted engine (they open `AsyncSessionLocal` = the privileged `DATABASE_URL`), so
  flipping `RLS_ENABLED` on a worker is nearly inert and proves nothing about the risky
  path. The only meaningful cutover is `coachlenz-backend`, so the safety mechanism is
  time-boxing + instant env revert, not service sharding.
- **Workers under RLS:** unchanged and correct — the cross-org job poll needs to see all
  orgs and does, on the privileged engine. Per-job `set_org_context` is future
  defense-in-depth (only needed if workers ever move onto the restricted engine).
- **Future tables:** the enable script and grants are dynamic/default-privileged, so a
  new org-scoped table added by a later migration is covered automatically — but re-run
  Step 2 + Step 3 (both idempotent) after any migration that adds tables, and before
  relying on the backstop for them.
