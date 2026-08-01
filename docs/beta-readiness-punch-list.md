# CoachLenz Beta-Readiness Punch List

**Reconciled 2026-08-01 against the live codebase.** Original evidence audit:
2026-07-30 (six parallel read-only sweeps). This document is the authoritative
current status; it supersedes any older "PR pending" notes. Statuses below were
re-verified in code on 2026-08-01, not carried over on faith.

## Bottom line (2026-08-01)

Every **P0 code item is DONE and merged.** Nearly all P1/P2 items are DONE. What
remains to actually launch and charge is almost entirely **yours, not code**: the
attorney's legal text, the Stripe dashboard config, `SENTRY_DSN` on the workers, and
confirming prod env vars. On the code side only small hardening/polish is left.

The core product (football + basketball loops: ingest -> multi-pass detection ->
tendency+coordinator engine -> failure-transparent report -> privacy-stripped shares)
is fully built, org-scoped, and defensively coded. This is not a scaffold.

---

## P0 — all DONE (code)

1. **Trial gave away the paid product** -> FIXED (#109). `entitlements.py`
   `assert_ready_to_analyze` (verify email + lock a sport, active-trial only) gates
   upload/URL-import/auto-detect; `assert_feature_allowed` blocks deep/grade analysis,
   multi-game reports, and film packages for trials. Verified in code.
2. **Legal + COPPA enforcement** -> CODE FULLY SHIPPED. Signup requires a Terms/Privacy
   checkbox, logged per user with IP (#112). The per-org student-data (COPPA/FERPA)
   attestation now gates ALL THREE minors'-data surfaces: roster (#112), film upload +
   URL import (#137), and manual scout sessions (#139). A Terms/Privacy re-consent modal
   fires on a version bump (#138). **YOURS:** the attorney finalizes the `-draft`
   ToS/Privacy/attestation text, then bump `*_VERSION` in `services/legal.py`.
3. **Worker failures invisible** -> FIXED (#110). `init_sentry()` runs in every worker
   (`BaseWorker.run_forever`) + the API; worker error paths `capture()`. **YOURS:** set
   `SENTRY_DSN` on the worker services (a no-op without it).
4. **Unbounded Opus spend** -> FIXED (#110). Default monthly analysis cap (300) when a
   coach has no explicit `CoachUsageLimit` row, + slowapi 20/min on `/ingest/url` and
   `/upload/file`.
5. **Player Grades fabricated data** -> FIXED (#111). Honest empty state + real-data
   distribution; the fake `SAMPLE_*` players/insight are gone (verified). Also fixed the
   "grades populate automatically" oversell copy.

---

## P1 — status

### Billing (Stripe ~90% built)
- **Enterprise tier 400** -> FIXED (#141). Enterprise is contact-sales; UI shows a
  Contact Sales CTA and `billing.CONTACT_SALES_TIERS` returns a clear message.
- **Webhook idempotency** -> FIXED (#140). `processed_stripe_events` (migration 036);
  redelivered events are claimed-or-skipped in one transaction. Kills the double
  referral-credit bug.
- **Annual billing not wired** -> OPEN. Only a monthly price per tier. Needs *you* to
  create annual Stripe price IDs, then a small `PRICE_MAP` restructure + interval field.
  **PRICING IS ON HOLD per Jay (2026-08-01) — do not touch until he says otherwise.**
- **Stripe checkout/portal calls not wrapped in try/except** -> OPEN (small hardening).
  `billing.py` `Customer.create` / `checkout.Session.create` / `billing_portal` raise a
  raw 500 on a Stripe outage. Low urgency; billing-adjacent (see pricing hold).

### Product honesty
- **"grades populate automatically" oversell** -> FIXED (#111).
- **Flag football is the lightest engine** (tendencies, no coordinator/scout layer) ->
  still TRUE. A positioning/copy note, not a bug. Lives on the marketing site (yours).

### Auth / API hygiene
- **Duplicate weak `/me/change-password`** -> FIXED. Removed; the single hardened
  `POST /auth/change-password` (length + reject-same + token_version revoke) is the only
  path. `me.py` has just a pointer comment. Verified.
- **Onboarding phone step could trap when Twilio unset** -> FIXED (#40). The phone gate
  no longer traps users when Twilio is unconfigured.

### Ops
- **`/health` liveness-only** -> FIXED. `/health` is cheap liveness; `/health/ready`
  pings the DB and returns 503 if Postgres is unreachable, so a broken deploy is not
  promoted. Verified in `main.py` + `health.py`.
- **DB connection exhaustion** -> FIXED. `models/base.py` sets an env-driven pool
  (`DB_POOL_SIZE=3` + `DB_MAX_OVERFLOW=4` -> 7/process, + timeout/recycle + pre_ping),
  Postgres-only so the SQLite test engine is untouched. Verified.
- **SIGKILL'd ingest strands a game in a spinner** -> FIXED both ends. Backend:
  `IngestWorker.on_dead_letter` marks the game `error` unless already ready/error
  (verified). Frontend: the import spinner now has a 7-min elapsed guard + a
  consecutive-error counter and resolves to a "still running, check your library"
  state (#144).

### Frontend
- **"Landing page thin/off-brand (`frontend/app/page.tsx`)"** -> PREMISE CORRECTED.
  `page.tsx` is the APP ROOT at app.coachlenz.com, a minimal internal page — NOT the
  public marketing landing. The real marketing site (coachlenz.com) is a separate,
  polished, on-brand page with full pricing (confirmed via Jay's screenshot 2026-08-01).
  So this item and "No public pricing page" below are effectively resolved by the
  marketing site. A rebuild of the app-root `page.tsx` was attempted and REVERTED at
  Jay's request. Do NOT touch outward-facing/marketing pages without a draft + explicit
  approval (see [[coachlenz-no-ship-outward-without-approval]]).
- **No public pricing page** -> resolved by the marketing site (see above).
- **Sport tabs unwired** -> FIXED. Non-interactive plan-sport indicators (spans), not a
  fake switch.

---

## P2 — status

- **Two design systems coexist** (`.clz` OSShell vs legacy gray back-office) -> INTENTIONAL
  per the back-office rebuild; reads slightly unfinished but is not a bug.
- **Survey feature dead code** -> FIXED. Router/worker/model removed; DB tables left (drop
  is destructive, not worth it).
- **`window.alert()` for errors** in admin/grades/reports -> OPEN (P2 polish; replace with
  toasts).
- **Presigned download URLs 7d** -> FIXED (24h `R2_PRESIGNED_EXPIRY_SECONDS`; app refreshes).
- **Access token survives logout up to 30 min** -> by design, documented.
- **Doc drift "2-game trial"** -> FIXED (limit is 1).
- **No cookie/consent banner** -> OPEN (jurisdiction-dependent; low urgency).

---

## Config & secrets — VERIFY in prod (yours)

Confirmed live during 2026-08 work: **R2** (HD film ingest works end-to-end -> R2 keys
are set), **ANTHROPIC_API_KEY** (detection + reports run), **RESEND** (emails configured),
**ADMIN_EMAILS** (`aiwithjaycoz@gmail.com`), **YOUTUBE_COOKIES** (the HD-ingest lever, on
`coachlenz-worker_ingest`).

Still to set/confirm:
- **`SENTRY_DSN`** on the worker services — still unset, so workers report nothing (P0 #3).
- **`FERNET_KEY`** and **`STRIPE_*`** (key / webhook secret / price IDs) when billing goes live.

Hygiene (small code, mine if you want it):
- **`ADMIN_PASSWORD` default is still `"ChangeMeNow!"`** (`config.py:101`). Inert today
  (`seed.py` refuses to seed on an empty env value), but change the default to `""` to
  remove the latent footgun.
- **`.env.example` has drifted**: lists Stripe price vars the code does not read, omits
  ~9 vars it does use (`ADMIN_EMAILS`, `RESEND_DOMAIN`, `FOUNDER_REPLY_TO`,
  `SECRET_KEY_PREVIOUS`, `FERNET_KEYS_PREVIOUS`, `WORKERS_IN_API`, `RLS_ENABLED`,
  `TRIAL_DAYS`, `MAX_UPLOAD_BYTES`), and shows the wrong `ANTHROPIC_MODEL`.

---

## What is genuinely solid (unchanged from the audit)

Auth security (hashed single-use reset tokens, refresh revocation via token_version,
timing-safe login, key rotation, default-deny admin); the SSRF guard (resolve-all-records,
re-checked at the sink); the job queue (skip-locked, heartbeats, watchdog, circuit breaker,
dead-letter); idempotent migrations; CORS lockdown + security headers; the multi-pass
detection engine with honest single-camera confidence reporting; report failure
transparency (two-audience); privacy-stripped share links; the "Powered by Cosby AI
Solutions" footer; and a real, implemented UATP transparency layer (identity disclosure,
confidence flagging, action logging, human escalation). API rate-limiting on auth.

---

## Net: what actually stands between here and charging money

1. **Attorney** finalizes the ToS/Privacy/attestation text -> bump `*_VERSION`.
2. **Stripe dashboard**: create products/prices (incl. annual), set `STRIPE_*` env, register
   the webhook, enable the Customer Portal. (Pricing on hold per Jay.)
3. **`SENTRY_DSN`** on the workers.
4. Small code polish if wanted: wrap Stripe calls, `ADMIN_PASSWORD` default, `.env.example`,
   `window.alert` -> toasts, cookie banner. None blocks launch.
