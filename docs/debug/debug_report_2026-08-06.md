# Build / Debug Journal — 2026-08-04 → 2026-08-06

Security, reliability & controls sprint. Itemized changes are in
[`/CHANGELOG.md`](../../CHANGELOG.md); this journal records the process, decisions,
deferrals, and how each change was verified. Chronological.

## Method
An adversarial audit of the backend fanned out across four surfaces — billing/
credits, auth/tenant-isolation, the analysis pipeline/workers, and FERPA/consent —
producing 24 findings. Each finding was re-verified against the source (exact
`file:line` + traced code path) before any fix. Every fix shipped with a test and
was checked against the full fast suite; each PR was verified live in production
after deploy (migration applied + healthcheck, and functional checks where
possible).

## Timeline

### 2026-08-04 — Tier-1 (PR #177, `d8a3c9b`)
12 HIGH findings (money / data-loss / PII): referral double-pay, two check-then-act
cap races, preview mis-charge, CSV student-field data loss, public report-title
leak, ingest event-loop freeze, per-batch client leak, detection token truncation,
recruiting disclosure audit, rate-limiter proxy collapse, SMS toll-fraud.
Migration 039. Verified live: migration applied, `/health/ready` 200.

### 2026-08-04 — Tier-2/3 (PR #178, `d214a40`)
11 findings + a partial #17 audit: checkout dup-subscription guard, cancellation
trial regrant, vision empty-response guard + timeout, `add_player` race → 409,
`clone_roster` height/weight, CORS dev-origin gate, batch parent-ownership,
unauth local-file fail-closed, `legal_acceptances` uniqueness. Migration 040.
Repaired 6 pre-existing red tests inherited from commit `2acd7ed`.

### 2026-08-05 — Rate limiter (PR #180, `8214ec2`)
Surfaced while verifying #11 live: `--proxy-headers` was confirmed active and NOT
spoofable (uvicorn resolves the real client IP; injected `X-Forwarded-For` ignored
— proven from the access log), but the limiter used in-memory per-worker storage,
so `--workers 4` meant ~4x the configured limit. Fixed with a shared **Redis**
store (provisioned a Railway Redis service, `REDIS_URL=${{Redis.REDIS_URL}}`).
Verified live: a 14-request login burst returned 401×10 then 429 — the shared
counter trips at exactly the configured limit (before, 33 requests couldn't trip
it).

### 2026-08-06 — Deferred #4 + #17 (PR #189, `af90527`)
Full-stack. #4a refund-on-failure (always on). #4b duplicate-run guardrail and #17
recruiting disclosure consent shipped **flag-gated, default off** (frontend +
backend deploy from the same repo; flags let them activate cleanly). Migrations
042, 043. Both flags then activated per Jay's call. Verified live in the browser:
the rerun confirm dialog surfaced the correct message (cancelled — no spend), and
the recruiting consent panel rendered with the attestation + checkbox (profile
stayed Private — gate held).

### 2026-08-06 — Feature-flag control panel (PR #190, `fe8b5bb`)
Runtime toggle plane (migration 044 `feature_flags` + Admin → Feature Toggles).
DB override of an env default, read per request with a ~20s per-worker cache,
degrades to the env default on any DB error. Verified live via the authenticated
API: `GET` returned correct states; a `PUT` round-trip flipped `recruiting_consent`
on then off (source → override).

### 2026-08-06 — Confirm modal (PRs #191 `e10a4b7`, #192 `f273a4e`)
Root cause of "delete buttons do nothing": native `window.confirm()` is
auto-cancelled in embedded/preview panes, so the guarded action bailed silently
(confirmed: `window.confirm()` returns `false` with no prompt in the pane).
Replaced every destructive `confirm()` with a DOM-rendered `ConfirmModal` — admin
org-delete, roster/report/film delete, staff revoke, recruiting disable, and the
duplicate-run prompt. `grep -r 'confirm(' app/` is now empty. Verified live: the
org-delete and film-delete modals open and cancel cleanly.

## Deferred / follow-ups
- **Recruiting attestation text** in `services/legal.py` is placeholder `-draft`
  (`RECRUITING_DIRECTORY_VERSION = 2026-08-05-draft`). Bump when the attorney
  finalizes; `recruiting_consent` is currently **off** pending that.
- **Feature flags have no "delete override"** endpoint — a `PUT` leaves a DB row,
  so a flag reads `source: override` after any toggle even if set back to the env
  default (functionally identical). See the runbook.
- **Other `confirm()`-style natives** (`alert()`, `prompt()`) were not swept beyond
  the admin error `alert()`; none are on a destructive path today.

## Verification summary
Full fast suite green at each merge (up to 411 passing). Every deploy confirmed
live: migration applied via the pre-deploy command + `/health/ready` 200, plus
functional spot-checks (rate-limit trip, rerun dialog, consent panel, feature-flag
round-trip, confirm modals). Test data created during verification (a roster player
+ smoke orgs) was cleaned up.
