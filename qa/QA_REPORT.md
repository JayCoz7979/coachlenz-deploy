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
