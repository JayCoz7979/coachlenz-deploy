# CoachLenz Beta-Readiness Punch List

Evidence-based audit of the whole product (2026-07-30), six parallel read-only
sweeps: backend API, frontend, auth/onboarding/entitlements, billing/config,
infra/observability, and product pipeline/legal. Severities are for a **paying**
beta. Items marked (verify prod env) may already be resolved by Railway env vars
this audit could not see.

## Bottom line

The core product is genuinely strong and beta-credible: the football and
basketball loops (ingest -> multi-pass detection -> tendency+coordinator engine ->
failure-transparent report -> privacy-stripped share links) are fully built,
org-scoped, and defensively coded. The auth stack, job queue, SSRF guard, and
migrations are production-grade. This is not a scaffold.

The gaps are narrow but real, and they cluster in exactly the places that matter
when money changes hands: **you would give the paid product away for free (broken
entitlement gating), you cannot see the failures most likely to hurt a paying
coach (workers report to nothing), you are legally uncovered for taking minors'
film and payment (consent/COPPA exist only as draft text), and one nav page shows
fabricated data.** None is architectural. All are fixable. Stripe itself is ~90%
built and small; it is NOT the real blocker.

---

## P0 — Must fix before charging a single dollar

### 1. Trial gives away the paid product (revenue leak) — FIXED (PR pending)
> Resolved by `backend/services/entitlements.py`: `assert_ready_to_analyze`
> (verify email + lock a sport, active-trial only) gates upload/URL-import/
> auto-detect; `assert_feature_allowed` blocks deep/grade analysis, multi-game
> reports, and film packages for active trials. Unit + integration tested.

- `is_feature_locked()` / `TRIAL_LOCKED_FEATURES` (`backend/services/trial.py:5,21`)
  are **dead code — zero call sites**. A trial org can run deep multi-pass
  analysis, multi-game reports, and film packages, all nominally trial-locked.
- Onboarding is **not a gate**: no analysis endpoint checks `email_verified` or a
  locked sport (`games.py:36`, `ingest.py:68`, `ai_detect.py:287` gate on sport
  only, and `sports.py:71` short-circuits to "allowed" when no sport is chosen).
  A user who registers (tokens issued immediately) and skips onboarding gets an
  **unverified, any-sport, fully-featured** trial.
- Fix: wire `is_feature_locked` into the analysis/report/package routers; require
  `email_verified` (ideally onboarding complete) before the first analysis.
- Size: small-medium code. **This is the highest-value fix on the list.**

### 2. Legal + COPPA have zero enforcement (you ingest minors' film)
- ToS/Privacy: thin 4-paragraph live pages (`frontend/app/terms/page.tsx`,
  `privacy/page.tsx`); the real 10KB drafts (`legal/*.md`) are **unreviewed
  ("ATTORNEY REVIEW REQUIRED", [FILL-IN] date) and rendered nowhere**.
- Consent is **text only** at signup — no checkbox, no logged acceptance, no
  `legal_acceptances` table anywhere in migrations/models.
- COPPA/minor handling is **aspirational only**: the words appear solely in the
  draft markdown, never in code. No under-13 gate on player-profile creation, no
  `student_consents` table, no age gate in onboarding.
- Fix (code, mine to build): consent checkbox + logged acceptance table; an
  under-13 / student-consent gate before player data is created. Fix (yours):
  attorney-finalize the ToS/Privacy drafts before onboarding any school.
- Size: medium code + your lawyer. Blocker for taking minors' film + money.

### 3. Worker failures are invisible (you can't see what breaks) — FIXED (PR pending)
> Resolved by `backend/observability.py`: `init_sentry()` is now called in
> `BaseWorker.run_forever()` (every worker process) as well as the API, and the
> worker error paths (job handle, process loop, dead-letter, watchdog) explicitly
> `capture()` to Sentry. Still a no-op without `SENTRY_DSN` — set it on the worker
> services. The `error_logs` table remains a separate follow-up.

- Sentry is initialized only in the API process (`main.py:28`). The dedicated
  worker services (`python -m backend.workers.worker_*`) never import it — `grep
  sentry backend/workers/` is empty. The heaviest, most crash-prone work (film
  ingest, multi-pass Opus detection) runs on exactly the services that report
  nothing; errors live only in Railway stdout.
- The CLAUDE.md-mandated `error_logs` table does not exist anywhere in `backend/`.
- Fix: init Sentry in the worker entrypoint (or add the `error_logs` write path).
- Size: small. Without it you are flying blind on paid workloads.

### 4. Unbounded Opus spend per beta user — FIXED (PR pending)
> Resolved: a generous default monthly analysis cap
> (`settings.DEFAULT_MONTHLY_ANALYSIS_LIMIT=300`) now applies when a coach has no
> explicit `CoachUsageLimit` row, so an absent row is no longer unlimited (explicit
> rows, incl. 0=unlimited, still win). Plus slowapi rate limits on the game-creation
> velocity vector: `/ingest/url` and `/upload/file` (20/min). The auto-detect
> trigger is bounded by the monthly cap + the existing `already_queued` dedup.

- The slowapi limiter is imported **only in `auth.py`**. `/games/{id}/auto-detect`,
  `/ingest/url`, `/upload/file`, and scout endpoints have no per-IP/per-org rate
  limit. The base "coach" plan has no `CoachUsageLimit` row, so the monthly cap
  check (`ai_detect.py:329`) is skipped -> **unlimited deep-Opus runs**. A leaked
  token or an eager coach can run up unbounded API cost.
- Fix: frequency rate-limit on the auto-detect trigger + a default coach cap.
- Size: small.

### 5. Player Grades page shows fabricated data — FIXED (PR pending)
> Resolved: `frontend/app/players/page.tsx` no longer ships `SAMPLE_PERFORMERS`,
> `SAMPLE_BANDS`, or the invented "top 3%" AI insight. It now shows an honest empty
> state (no data today, since `/players` 404s) that also sets the real expectation
> (grading is opt-in and needs legible HD film), and a real-data path that derives
> the grade distribution from actual grades. Also addresses the P1 "grades populate
> automatically" oversell copy.

- `frontend/app/players/page.tsx` renders hardcoded fake players ("Marcus J.",
  "Devon W.") and an **invented AI insight** ("top 3% in our library"). `GET
  /players` 404s (no backend), so it is always in preview, and the fake grade
  bands + insight render **unconditionally** (not gated by `isPreview`). It is a
  live nav item a paying user will click.
- Fix: hide the page (or the fabricated blocks) until a real endpoint exists.
- Size: small. Integrity issue — do not ship invented data to paying users.

---

## P1 — Fix before broad beta (money can flow, but these bite)

### Billing edges (Stripe is ~90% built; these are the unfinished corners)
- **Enterprise tier is broken**: the UI offers an `enterprise` card
  (`frontend/app/settings/billing/page.tsx:35`) but `PRICE_MAP`
  (`billing.py:16`) has only coach/athletic_dept/district -> clicking 400s.
- **Annual billing advertised but not wired**: UI shows annual prices; `PRICE_MAP`
  maps each tier to a single monthly price ID. Every checkout bills monthly.
- **No webhook idempotency**: `invoice.payment_succeeded` (`billing.py:110`)
  creates a `referral_credit` job with no dedup on `event["id"]`; Stripe
  redelivery = duplicate referral credits.
- **Stripe calls not wrapped** (`billing.py:38,42,56`): a Stripe outage/bad price
  raises a raw 500 at the checkout moment. Wrap in try/except -> clean error.
- Go-live (config, yours): create products/prices in Stripe, set
  `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`/`STRIPE_PRICE_*`, register the
  `/billing/webhook` endpoint, enable the Customer Portal.

### Product honesty (overselling vs. reality)
- "All sports" = 3 engines, and **flag football is the lightest** (tendencies but
  no coordinator/scout layer; `engine.py:91` adds scout only for football).
- "grades populate automatically" (`players/page.tsx:71`) oversells: player/jersey
  tracking silently needs **720p+** film (`worker_ingest.py:359`) while the default
  YouTube path on Railway is throttled to **360p**, and play-grading ships
  **disabled** (`PLAY_GRADE_ENABLED=False`). Reword to match reality.

### Auth / API hygiene
- **Duplicate weak `/me/change-password`** (`me.py:75`): unlike `auth.py:216` it
  does NOT bump `token_version` (no session revocation), skips length/difference
  checks. Retire it; frontend already uses the strong one.
- **Onboarding phone step can trap** (`frontend/app/onboarding/page.tsx:82`): hard-
  jumps to phone even if Twilio is unset; 503 with no skip button until reload.
  Latent while Twilio stays configured.

### Ops
- **`/health` is liveness-only** (`main.py:128`): never touches the DB, so an
  instance with a dead Postgres or failed migration still reports healthy and
  serves 500s. Add a `/readyz` that pings the DB.
- **DB connection exhaustion risk**: `railway.toml` runs `uvicorn --workers 4`;
  `models/base.py:5` sets no `pool_size`/`max_overflow` -> ~15 conns/process ->
  ~60 from the API alone + worker services, against a small Postgres (~100 max).
  Set an explicit pool size.
- **SIGKILL'd ingest strands a game in a permanent spinner**: `IngestWorker` has no
  `on_dead_letter` override, so an OOM mid-handle leaves `Game.status=processing`
  forever (ai_detect is rescued by `detect_status` self-heal; ingest is not).
  Mirror the reports/ai_detect recovery.

### Frontend
- **Landing page is thin and off-brand** (`frontend/app/page.tsx`): one hero + two
  buttons, no features/pricing/social proof, and uses **purple/gray** — a direct
  violation of the CGE green/gold "no blue/purple" brand rule.
- **No public pricing page**: pricing lives only behind login at
  `/settings/billing`. A prospect cannot see prices before signing up.
- **Sport tabs unwired** (`components/os/OSShell.tsx:144`): per-sport tabs render
  with no onClick; `activeSport` is hardwired. Multi-sport orgs can't switch.

---

## P2 — Polish / nice-to-have

- **Two design systems** coexist: `.clz` green/gold OSShell (dashboard/intel/
  reports/games) vs. legacy gray Tailwind (admin/ad/settings/billing) — a visible
  theme jump. (Intentional per the back-office rebuild, but reads unfinished.)
- **Survey feature is dead code**: `routers/survey.py` is not mounted in `main.py`;
  `worker_survey.handle()` is a no-op; nothing enqueues survey jobs. Remove or wire.
- `window.alert()` used for errors in admin/grades/reports. Replace with toasts.
- Presigned **download** URLs default to 7 days (`config.py:27`) — shorten.
- Access token survives logout up to 30 min (by design; documented).
- Doc drift: `sports.py:37` says "2-game trial" but the limit is 1.
- No cookie/consent banner (jurisdiction-dependent).

---

## Config & secrets to VERIFY in prod (this audit cannot see Railway env)

These silently fail if unset; confirm each is set on the relevant service:
- **R2** (`R2_ACCOUNT_ID`/`_ACCESS_KEY_ID`/`_SECRET_ACCESS_KEY`): if unset, uploads
  silently route to ephemeral `/tmp` and **all film is lost on redeploy** — no
  error. Highest-severity silent failure. (`r2.py:_use_local()`)
- **FERNET_KEY**: empty -> `MultiFernet([])` throws at first encrypt (Hudl creds,
  encrypted fields).
- **ANTHROPIC_API_KEY**: empty -> report + detect workers 401; core product no-ops.
- **RESEND_API_KEY**: empty -> welcome/verify/report emails throw (not guarded like
  Twilio).
- **STRIPE_*** (key, webhook secret, 3 price IDs): unset -> billing 401/400.
- **ADMIN_EMAILS**: must be set (e.g. `aiwithjaycoz@gmail.com`) for admin access.
- **SENTRY_DSN**: unset on workers regardless (see P0 #3).

Hygiene:
- **`ADMIN_PASSWORD` defaults to `"ChangeMeNow!"`** committed in `config.py:88`.
  `seed.py` reads the env directly and refuses to seed if empty, so it is inert
  today — but change the default to `""` to remove the latent footgun.
- **`.env.example` has drifted**: lists Stripe price vars the code does not read
  (`STRIPE_PRICE_STARTER_*`, `_PROGRAM_*`, `*_MONTHLY/_ANNUAL`), omits ~9 vars the
  code does use (`ADMIN_EMAILS`, `RESEND_DOMAIN`, `FOUNDER_REPLY_TO`,
  `SECRET_KEY_PREVIOUS`, `FERNET_KEYS_PREVIOUS`, `WORKERS_IN_API`, `RLS_ENABLED`,
  `TRIAL_DAYS`, `MAX_UPLOAD_BYTES`), and shows the wrong `ANTHROPIC_MODEL`. A
  deployer following it would misconfigure billing and miss key rotation vars.

---

## What is genuinely solid (so the picture is balanced)

Auth security (hashed single-use reset tokens, refresh revocation via
token_version, timing-safe login, key rotation, default-deny admin); the SSRF
guard (resolve-all-records, re-checked at the sink); the job queue (skip-locked,
heartbeats, watchdog, circuit breaker, dead-letter); idempotent migrations; CORS
lockdown + security headers; the multi-pass detection engine with honest
single-camera confidence reporting; report failure transparency (two-audience);
privacy-stripped share links; the "Powered by Cosby AI Solutions" footer; and a
real, implemented UATP transparency layer (identity disclosure, confidence
flagging, action logging, human escalation). API rate-limiting on auth. This is a
strong solo build.
