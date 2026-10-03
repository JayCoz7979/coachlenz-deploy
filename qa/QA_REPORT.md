# CoachLenz QA Report

## Run: 2026-10-02 — focus: AI video detection reliability & accuracy

Per the mid-run steer, this pass centers on **AI video detection reliability and
accuracy** (the trust-maker), with the other workflows audited secondarily.

### Detected context
- Product: CoachLenz (FastAPI backend + Next.js frontend, Railway Postgres + Cloudflare R2; NOT Supabase for app data).
- Backend: `https://coachlenz-backend-production.up.railway.app` (routers at root).
- Frontend: `frontend/`, Next.js app-router; `NEXT_PUBLIC_API_URL` -> the Railway backend.
- Live outbound (prod): Resend email, Stripe, Anthropic vision (real COGS $4-13/run), funnel telemetry.
- Detection engine: `backend/workers/worker_ai_detect.py` (3-pass Claude vision), `backend/workers/worker_ingest.py` (ingest + probe), tendency/scout engines under `backend/services/tendency_engine/`.

### Scope & method (honest)
Production has live server-side outbound and real COGS, and there is no runnable
local backend in this environment, so **write / auth / analysis workflows were NOT
driven live** (that would fire real email/Stripe/Anthropic). This pass is:
1. **Real production-data verification** of detection reliability (job outcomes, error
   taxonomy, measured cost, confidence/needs-review) read from `jobs` + `agent_logs`.
2. **Code-level audit** of the detection pipeline and the workflows that can't be driven live.
3. **Live read-only** public-surface smoke (local dev server; API-dependent paths not testable locally because there is no local backend).
No live outbound fired. No `QA_` records or QA users were created (no safe write path existed), so none needed removal.

---

## Pass/Fail summary

| Area | Verdict | Basis |
|---|---|---|
| Detection reliability (job success) | **FAIL** (15% failure rate) | prod `jobs`: 67 done / 12 error |
| Detection accuracy (reads) | PASS (single-cam caveat) | engine audit + prior DHHS verification; known ~68% night recall ceiling |
| Ingest + duration probe | FIX APPLIED | #257 + this pass (`-rw_timeout`, fallback) |
| Event persistence (money path) | FIX APPLIED | QA-01 crash fixed |
| Frame extraction / temp cleanup | FIX APPLIED | QA-03 fixed |
| Cost / margin | PASS (watch deep) | avg $5.87, max $13.23 vs $13.48 deep ceiling |
| Public pages render | PASS | landing/book render; dev-only API errors are not prod findings |
| Auth / CRUD / tenant isolation | NOT LIVE-VERIFIED | code-audited only (can't log in / no local stack) |

**Production reliability snapshot (real):** ai_detect jobs 67 done / 12 error = **15.2% failure**. 44 completion logs: 4,251 plays, **1,479 needs-review (34.8%)**. 26 cost logs: avg **$5.87**, max **$13.23**. 7 agent_log error-phase entries (UATP failure transparency firing).

---

## Findings

### QA-01 — Detection run crashes on a non-string `event_type` (asyncpg DataError) — HIGH — FIXED
- **Location:** `backend/workers/worker_ai_detect.py`, event persistence (`event_type=p.get("event_type", "shot")`).
- **Workflow/step:** basketball detection -> persist events.
- **Evidence (prod):** `jobs.error_message` = `(asyncpg) DataError: invalid input for query argument $16: False (expected str...)`.
- **Expected vs actual:** a stray model value should be coerced; instead a bool/number for `event_type` hit the NOT NULL string column and **aborted the entire paid run** (coach gets nothing, credits refunded).
- **Root cause:** `event_type` was the one unguarded string field in the insert; every other string went through `_s()` (which nulls bools) but `event_type` passed the raw model read for basketball. `time_seconds` was also raw.
- **Fix applied:**
```python
# event_type is NOT NULL; coerce the basketball model read (a stray bool/number
# crashed the whole run with asyncpg "invalid input ... expected str").
event_type=(_s(p.get("event_type")) or "shot") if sport == "basketball" else "play",
side=_side(p),
time_seconds=_f(p.get("time_seconds")),   # new _f(): float-or-None, never a bool
```
plus a new `_f` helper beside `_s/_int/_b`:
```python
def _f(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
```

### QA-02 — Duration probe over R2 is the #1 failure cause — HIGH — MITIGATED
- **Location:** `worker_ai_detect._probe_duration` + `worker_ingest._probe`.
- **Evidence (prod):** 6x `Could not determine video duration` + 1x the new diagnosable form `...(ffprobe host=...r2.cloudflarestorage.com): ...AWS4-HMAC-SHA256...` = ffprobe failing to read the R2 presigned URL. This is ~half of all failures.
- **Expected vs actual:** a transient R2 read failure should fall back, not crash. Historically it hard-crashed with an opaque message and no fallback when the game had no stored duration.
- **Root cause:** both probes read only `format.duration`; some containers leave it empty, and ffprobe-over-R2 can fail transiently. If ingest's probe also failed, `duration_seconds` stored 0, leaving detection no fallback.
- **Fix:** #257 (merged) added `duration_from_probe` (format OR stream OR tag), a retry, the stored-duration fallback, and a diagnosable error. **This pass adds** `-rw_timeout 30000000` to both probes so a stuck R2 read fails fast into the retry instead of hanging to the 90s wall.
- **Residual (sign-off):** the rare case where BOTH ingest and detect ffprobe fail still has no duration source. Durable fix (backlog QA-10): capture duration client-side at upload and store it, so detection always has a fallback independent of ffprobe-over-R2.

### QA-03 — Temp-dir cleanup race fails an otherwise-successful run — HIGH — FIXED
- **Location:** `worker_ai_detect._detect_plays`, `tempfile.TemporaryDirectory()` wrapping frame extraction.
- **Evidence (prod):** `jobs.error_message` = `[Errno 39] Directory not empty: 'window_0013'`.
- **Expected vs actual:** a lingering ffmpeg write at teardown should not fail a run whose plays were already detected; instead `TemporaryDirectory` cleanup raised and failed the job.
- **Root cause:** default `TemporaryDirectory` cleanup raises on a non-empty dir (a window dir still being written by a slow ffmpeg at teardown).
- **Fix applied:**
```python
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as frames_dir:
```

### QA-04 — Deleted-mid-run game crashes persist with "No row was found" — MEDIUM — FIXED
- **Location:** `worker_ai_detect._detect_plays` persist block, `result.scalar_one()`.
- **Evidence (prod):** `jobs.error_message` = `No row was found when one was required`.
- **Expected vs actual:** if a coach deletes a game while it's analyzing, the run should stop cleanly; instead `scalar_one()` raised and the run errored.
- **Fix applied:**
```python
g = result.scalar_one_or_none()
if g is None:
    logger.warning(f"[ai_detect] game {game_id} vanished before persist; skipping save")
    return {"game_id": game_id, "plays_detected": 0, "skipped": "game_deleted"}
org_id = g.organization_id
```

### QA-05 — Re-run blocked by a stale "analyzing" status — MEDIUM
- **Evidence (prod):** 1x `Game not ready for detection (status=analyzing)`.
- **Detail:** the trigger returns `already_queued` for a genuinely active job and reconciles stale "running" jobs via a 10-min cutoff, but a game stuck in `status=analyzing` with no live job can block a re-run.
- **Fix direction:** the worker's `finally` already resets status to `ready`; add the same stale-cutoff status reconcile for `status=analyzing` (not just the job row) in the trigger so an orphaned analyzing state self-heals. Low frequency.

### QA-06 — Circuit-breaker dead-letter — MEDIUM — RESOLVED BY QA-01/02/03
- **Evidence:** 1x `Gave up after 3 failed attempts`. This is the MAX_ATTEMPTS breaker firing on a job that repeatedly hit QA-01/02/03. Fixing those removes the cause.

### QA-07 — Event batch insert is all-or-nothing on the money path — MEDIUM
- **Location:** persist block, `db.add_all(events); await db.commit()`.
- **Detail:** one malformed play fails the whole commit, losing the entire paid run (the mechanism behind QA-01). QA-01 removed the known trigger, but any future unanticipated bad field would again nuke the run.
- **Fix direction:** on commit failure, roll back and insert per-row, dropping and logging the offending play so the coach keeps the rest. Not shipped this pass (a rollback-reuse path in the money flow needs its own test before it goes in).

### QA-08 — 34.8% of plays flagged "needs your eyes" — MEDIUM (accuracy/trust, not a bug)
- **Evidence:** 1,479 / 4,251 plays flagged needs_review.
- **Detail:** honest single-cam uncertainty (consistent with the ~68% night-recall ceiling), but a third of plays flagged can read as "the AI isn't sure" to a coach. Not wrong, but a trust surface.
- **Fix direction:** frame it in the UI as "N flagged (single-camera limit), verify these" rather than a bare count, and consider whether `ESCALATION_THRESHOLD` is tuned right once there is coach-correction data to calibrate against.

### QA-09 — Deep-run cost near the margin ceiling — LOW
- **Evidence:** max run $13.23 vs the deep+grade football ceiling $13.48 at the cheapest ($0.70) bundle.
- **Fix direction:** monitor deep-run cost; if it trends up, raise deep credit cost or the floor bundle price. Already tracked by the detection-quality/analysis-cost admin views.

### QA-10 — Durable duration capture (backlog, see QA-02 residual) — LOW
- **Fix direction:** probe duration client-side at upload and persist it, so detection never depends on ffprobe-over-R2 for the fallback.

### QA-11 — Tenant isolation not live-verified this pass — MEDIUM (sign-off)
- **Detail:** isolation is app-layer `organization_id` filters (no DB RLS; the RLS backstop PR #148 is a dormant draft). Audited no-leak previously, but NOT re-verified live with two accounts this pass (can't log in / no local stack).
- **Fix direction (sign-off):** before launch, run the committed cross-account spec against a local dry-run stack with two QA users, confirming `qa_user_b` cannot read/edit/delete `qa_user_a` records by direct ID/URL.

### Public surface (dev smoke) — INFORMATIONAL
- Landing renders with no uncaught crash. The `ERR_CONNECTION_REFUSED` console errors are the dev frontend hitting `localhost:8000` with no local backend; **not a prod finding** (prod points at the Railway backend). API-dependent public paths (/sample, lead capture) were not testable locally.

---

## Fix log (this pass)
Applied to `worker_ai_detect.py` / `worker_ingest.py`:
- QA-01: `event_type` + `time_seconds` coerced (new `_f` helper). Kills the asyncpg crash class on the money path.
- QA-03: `TemporaryDirectory(ignore_cleanup_errors=True)`.
- QA-04: `scalar_one_or_none()` + clean skip on a deleted game.
- QA-02: `-rw_timeout 30000000` on both ffprobe calls (on top of #257's fallback+retry+diagnosable error).

**Judgment calls:** did not ship QA-07 (per-row salvage) into the money path without its own test; did not alter `ESCALATION_THRESHOLD` (QA-08) without coach-correction data to calibrate. Both are backlog.

**Human sign-off needed:** QA-11 (live two-account isolation on a dry-run stack) and QA-10 (client-side duration capture) before calling detection launch-hardened; plus the non-detection launch blockers (legal `-draft` text, Stripe price IDs) called out separately.

**Safety confirmation:** no live email/SMS/Stripe/Anthropic call fired; no `QA_` data or QA users created; production was read-only.

---

## Backlog (Medium / Low)
- QA-05 — stale `analyzing` status can block a re-run (self-heal in the trigger).
- QA-07 — event batch insert all-or-nothing; add per-row salvage on commit failure.
- QA-08 — 34.8% needs-review; frame as single-cam limit + calibrate threshold later.
- QA-09 — deep-run cost near margin ceiling; monitor.
- QA-10 — capture + store duration at upload (durable fix for QA-02 residual).
- QA-11 — live cross-account isolation verification on a dry-run stack.

---

## Run: 2026-10-02 (b) — instinct campaign (Steps A/B/C/I)

Acting on the instinct hardening prompt. Ran the read-only + safe-fix portion; the
write/local-stack steps are owner-gated (flagged below). No live outbound fired, no
prod writes, no QA users/data, $0 COGS (verified from logged data only).

### Step A — confirm-still-green (deployed code, read via railway ssh)
| Fix | Marker | Status |
|---|---|---|
| #258 temp-dir cleanup | `ignore_cleanup_errors` present | PASS |
| #258 event coercion | `_f` helper present (4 refs) | PASS |
| #258 ffprobe timeout | `-rw_timeout` present (both probes) | PASS |
| #258 deleted-game guard | `scalar_one_or_none` in persist | PASS |
| #257 duration | `duration_from_probe` in utils/media.py | PASS |
| accuracy (#240/#250) | court_zones + low_sample present | PASS |
| CODE_VERSION | was `multipass-v28`; #258 did NOT bump it | FIXED -> `v29-reliability` this run |

### Step B — re-measure failure rate
ai_detect jobs now: 67 done / 12 error (unchanged from baseline). Expected: #258
merged minutes ago, so there are no post-fix runs yet. The fixes prevent recurrence
going forward; a true drop can only be read once organic runs accumulate (new runs
cost COGS, so we do not force them). ACTION: re-read this after ~10 real runs.

### Step C — accuracy deep-dive (read-only, decrypt_json, no re-run)
Game inspected: `b5ed3bbb` "CTN: Elk River at Coon Rapids Boys BB" (265 auto plays,
~83 min). CRITICAL CONTEXT: this is an **Aug-1 run that PREDATES the accuracy fixes**,
so it reflects the OLD engine, not current behavior.
- side offense 159 / defense 99 / transition 7 (plausible balance).
- **34 timeouts** (phantom; NFHS allows ~10) — the pre-#105 over-tag bug.
- **0 free throws across 18 fouls** — FT recognition (v27) postdates this run.
- **mixed result labels "Good" (43) + "Made" (38)** — pre-fix vocabulary; current engine uses "Made"/"Missed" (verified on DHHS).
- **1 turnover in a full game** — suspicious under-detection; cannot tell if current engine still does this without a post-fix full-game run.
- zones look correct (wing-3s present and now counted post-#240).

Conclusions:
1. Current-engine accuracy is verified clean on the post-fix DHHS game (earlier run).
2. FINDING QA-12 (Medium): **old stored analyses still show pre-fix reads** (phantom timeouts, no FTs, mixed labels). A coach opening an old game sees the worse data. Fix direction: stamp each game with the CODE_VERSION it was analyzed under and surface "analyzed under an older engine, re-run for the current read" when it is behind; or batch-flag pre-v27 games. Do NOT auto re-run (COGS).
3. FINDING QA-13 (Medium, owner): **turnover recall on the current engine is unverified**; the only full game available is pre-fix. Needs ONE post-fix full-game run (COGS) to measure, ties to the standing full-game benchmark.

### Step I — public share-route 500 (HIGH, FIXED)
- Location: `backend/routers/reports.py::view_shared_report` (`GET /reports/{report_id}/share/{token}`, public + unauthenticated).
- Confirmed root cause by reading the route: `report_id: str` is queried against the UUID `TendencyReport.id`; a non-UUID (e.g. `/reports/1/share/x`) fails the uuid cast -> unhandled 500. A valid-but-unknown UUID already returns a clean 404.
- Fix applied: validate `report_id` as UUID at the top; malformed -> 404 (same as unknown), no 500.
```python
try:
    _uuid.UUID(str(report_id))
except (ValueError, AttributeError, TypeError):
    raise HTTPException(status_code=404, detail="This share link is invalid.")
```

### Owner-gated / not done this run
- Steps D (client-side duration capture), E (per-row event salvage), F (stale-analyzing self-heal), G (live two-account isolation), H (needs-review copy reframe): queued as the next PR wave. G requires a LOCAL dry-run stack with two QA users (O3) which does not exist in this environment; it cannot be run against prod.
- O1 prod queries: Step A/B/C above are the read-only results. O4 launch blockers (legal text, Stripe prices) remain Jay's.

### Backlog additions
- QA-12 — stamp games with analysis CODE_VERSION; surface "re-run for current engine" on pre-v27 games.
- QA-13 — measure turnover (and overall) recall on a post-fix full-game run (owner/COGS).

---

## Run — 2026-10-02 (wave 2, instinct detection hardening) — Opus

Lens: grumpy 40-year consultant. Focus: AI video detection RELIABILITY (the #1 trust-maker). Prod read-only; no live outbound; no COGS re-runs. Shipped on PR #260 (base main), CI green (unit + integration + lint + frontend build). Hard rule honored: a coach's prior runs are never auto-deleted.

### Shipped
- **QA-07 (High) — per-row insert salvage.** `worker_ai_detect.py` persist: each play inserts in its own SAVEPOINT (`begin_nested`). One malformed row is dropped+logged instead of failing the whole commit and losing every good play. Stays inside the transaction that already archived+cleared the prior run (run-preservation #239), so a prior run is never lost; if the new run saves nothing it rolls back and leaves the prior run ACTIVE and untouched.
- **QA-10 (High) — durable video duration.** Browser measures duration on file-select (hidden `<video>`, timeout-guarded) and sends it; `create_game` persists it as the detector fallback up front; ingest no longer clobbers a good stored duration with 0 on probe failure. No migration (`games.duration_seconds` already exists + already used as the detect fallback). Kills the #1 historical "Could not determine video duration" fault.
- **QA-08 (Medium) — single-camera honesty.** Game coverage scorecard reframes the "need your eyes" count as an honest single-camera limit, not an error. Copy only.

### Confirmed already-handled (no redundant code)
- **QA-05** stale `status=analyzing` self-heal: status endpoint resets to ready when the job is inactive; trigger cleans orphaned jobs and allows the re-run.
- **Run preservation (#239)** re-verified intact before touching the persist path.

### Not in scope this run (owner-gated / COGS)
- QA-11 live two-account tenant isolation (needs a local dry-run stack with outbound keys unset).
- QA-13 full-game recall re-measure on the current engine (real Anthropic COGS — owner decision).

---

## Run — 2026-10-02 (legal/consent readiness, instinct lens) — Opus

Lens: grumpy 40-year consultant. Scope: the last compliance launch item — COPPA/FERPA + legal consent. Static/adversarial review (prod read-only, no outbound, no COGS). Shipped on a branch + PR, CI green. HARD LINE held: no "ATTORNEY REVIEW REQUIRED" banner removed, no version flipped off `-draft` — binding minors'-data text is counsel's, not mine to fake.

### Findings + fixes shipped
- **L-1 (High) — subprocessor list was factually wrong.** Drafts named Supabase (DB) and Twilio (phone verification); reality is Railway PostgreSQL and no SMS (email is the sole identity gate, Twilio removed). A school-signed DPA naming unused vendors + omitting the real DB host is a defect. Corrected `legal/privacy-policy.md`, `legal/data-privacy-agreement.md`, `legal/README.md`.
- **L-2 (Med) — cookie-policy analytics placeholder.** Verified no analytics in code; replaced the `[FILL-IN]` with a definitive "no analytics cookies" statement.
- **L-3 (Med) — manual play tagging had no student-data gate.** `POST /events` + `/events/bulk` wrote student jerseys with ownership-only. New orgs are covered transitively (game creation is gated) but the guarantee was implicit + left a legacy edge. Added `assert_student_consent` to both + a regression test (`test_bulk_events_blocked_without_student_consent`); updated the positive bulk test for the new consent check.

### Verified complete (no code needed)
- Consent enforcement covers every minors'-data first-touch (auth, games, ingest, roster ×3, live, scout ×2, onboarding, recruiting, now events). Per-org attestation model: no new org can store a minor's data without attesting first.
- Re-consent on version bump is wired (ReconsentGate + /legal/accept-latest).

### Open (owner / counsel / follow-up build)
- Attorney review of the minors'-data terms + venue/effective-date `[FILL-IN]`s, then the one-step version bump (docs/legal/legal-readiness-2026-10-02.md).
- Public routes for full Privacy/DPA/Parents' Bill of Rights (NY §2-d) + a parent delete-request flow — recommended before onboarding real schools.

---

## Run — 2026-10-02 (COPPA deletion flow, instinct lens) — Opus

Lens: grumpy 40-year consultant. Target: the NEW parent data access/deletion flow (PR #264) — public intake + DESTRUCTIVE, irreversible deletion of a minor's data. Adversarial code audit against the real data model; prod verified READ-ONLY (route 405 / admin 403 / status 404). Fixes shipped on a branch + PR.

### Findings + fixes
- **QA-D1 (HIGH) — incomplete erasure.** `execute_deletion` scrubbed only LIVE events; the child's jersey still lived in `analysis_run_archives.plays` (JSON snapshots of prior runs). A parent "delete everything" that leaves the kid in archived snapshots is a COPPA failure. FIX: the deletion now also scrubs the jersey from archived run snapshots for that team's games (reassigns the JSONB so the change persists); whole-game deletion already cascades archives. Certificate + audit report the archived-plays count. Test proves archived snapshots are de-identified and teammates untouched.
- **QA-D2 (MED) — no preview before an irreversible action.** Fulfill deleted immediately on pasted IDs (fat-finger = wrong irreversible deletion + a certificate emailed). FIX: `POST /admin/privacy-requests/{id}/preview` runs `execute_deletion(dry_run=True)` — computes exact counts/players WITHOUT mutating, deleting, or flushing (then rolls back defensively). The admin UI now REQUIRES a Preview before the Delete button enables. Test proves dry-run writes nothing.
- **QA-D3 (MED) — verification evidence not captured.** Verify recorded only THAT an admin clicked, not HOW identity was confirmed. FIX: `verification_method` is now required on verify (400 if blank), stamped into the audit log with the admin's email; UI gates the Verify button on it.
- **QA-D4 (LOW) — unbounded public intake fields.** FIX: Pydantic `max_length` caps on every intake field so the public form can't bloat storage.

### Confirmed safe (no change needed)
- Admin endpoints are `require_admin` (prod 403 verified); public status is `secrets.compare_digest` token-gated; malformed request_id → 404 (not 500).
- Deletion is ORG-SCOPED on every query — a roster_player/game id from another org is a no-op, not a cross-tenant delete. Season/team scoping means a jersey reused on another team is not touched.
- HTML-injection closed in the prior commit (every requester field `html.escape`d into emails/cert; test).
- Intake rate-limited 5/min.

### Open / honest gaps (documented, not blocking)
- Identity verification remains human-gated (admin confirms with the school). That is defensible for a school-consent product and now has a recorded method, but there is no automated proof the requester is the parent — a known, accepted limitation to revisit with counsel.
- Access-request data compilation is still admin/out-of-band (no automated export).
