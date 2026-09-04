# CoachLenz Architecture: the value path

This document traces the retention-critical spine of CoachLenz, the path from a new
coach signing up to the product proving it retains. It is scoped to that spine on
purpose (onboarding to first value, core delivery, the learning loop, and retention
telemetry), not the whole feature surface. File and table references are current.

Stack: Next.js 14 frontend, FastAPI backend, Postgres, Cloudflare R2 for film, Claude
for detection and reports. Workers run out of process from the API.

## 1. Onboarding to first value

Signup creates an organization and a user. Identity is gated by email verification
(`routers/auth.py`, migration 019). Onboarding then locks the sport(s) the tier allows
(`routers/onboarding.py`, `services/sports.py`, migrations 018/020); the lock is enforced
at every film-analysis entry point so a coach cannot analyze a sport they did not buy.

First value is a film-analysis report, and it is never delivered off an empty state: an
analysis is always bound to a specific game's ingested film. The coach brings real film
in first (upload or a source URL), which is what makes the first experience genuine.

## 2. Core value delivery (the value moment)

The recurring value moment is: a coach ingests a game's film and receives an AI
film-analysis report they act on.

- **Ingest:** `routers/upload.py`, `routers/ingest.py`, and `workers/worker_ingest`
  bring film to Cloudflare R2 (`services/r2.py`), including HD YouTube/Hudl ingest.
- **Detection:** `routers/ai_detect.py` enqueues a job; `workers/worker_ai_detect.py`
  runs 3-pass Claude vision detection and writes events. A successful run records one
  `analysis_usage` row; a failed or dead-lettered run DELETES that row so the coach is
  not charged for undelivered analysis. This makes `analysis_usage` the honest record of
  a delivered core action (see section 4).
- **Report:** `workers/worker_reports` with `services/report_writer.py` composes the
  report (LLM voice over deterministic stats). Coaches read it and edit tagged plays.

## 3. Learning loop (per account)

When a coach edits a play the AI tagged, the change is captured as a label correction
(`coach_label_corrections`). When the same mislabel is corrected the same way enough
times, an account adjustment is proposed (`account_learning_adjustments`) that the coach
can accept; an active adjustment relabels matching plays in that account's future
reports. A rolling per-account quality score is kept (`label_quality_scores`). All
org-scoped, no credits consumed, and a coach can opt out to Manual Mode. See migration
034 and `services/learning_loop.py`, `routers/learning.py`. This is the product's
compounding advantage: the model of each account gets truer the more the coach uses it.

## 4. Retention telemetry (the gate)

Retention is DERIVED from real events, not stored in a new table, so it cannot drift
from or fabricate the truth. The two inputs are `organizations.created_at` (the signup
cohort) and `analysis_usage.created_at` (delivered core actions, self-healed on failure
per section 2).

- **Cohort:** the ISO week an organization signed up.
- **Activation (action metric):** share of a cohort whose first analysis lands within 7
  days of signup.
- **Return (return metric):** share of a cohort whose second analysis lands within 30
  days of signup. This is the gated number.
- **Maturation:** a cohort counts toward the verdict only once every member's 30-day
  window has closed; in-window cohorts read as "maturing" and never trip the stop line.

`backend/services/retention.py` holds the pure, unit-tested computation and the gate
constants. `GET /admin/retention` (gated by `require_admin`) serves per-cohort numbers
and a matured-cohort summary to the founder only. The Admin panel "Retention" tab renders
them. This surface is deliberately separate from the Athletic Dept usage dashboard
(`routers/ad.py`): the same events answer a different question.

The gate thresholds and the discipline rule they enforce are in
[BUILD_STATUS.md](BUILD_STATUS.md).

## 5. Conversion funnel (the conversion gate)

The conversion funnel measures visitor -> completed signup, and it stops where
retention starts. First-party only, no third-party trackers, no PII.

- **Events:** `funnel_events` (migration 045). Anonymous top-of-funnel steps
  (`landing_view`, `cta_click`, `signup_view`) arrive via a public rate-limited beacon
  (`POST /funnel/event`), keyed by a random localStorage `anon_id` and counted as unique
  visitors. The two signup steps (`signup_start`, `signup_complete`) are emitted
  server-side from `routers/auth.py` and `routers/onboarding.py`, so the browser cannot
  forge a conversion. All writes are best-effort and never block signup.
- **Metric:** `backend/services/funnel.py` (pure, unit-tested) turns events into step
  counts, step-to-step conversion, the single biggest drop-off, and the gate verdict.
  The gated number is completed signups per unique landing visitor.
- **Surfaces:** `GET /admin/funnel` (require_admin) and the Admin "Funnel" tab.
- **Lead capture:** `marketing_leads` + `POST /leads` capture a non-converter's
  volunteered email so they can be nurtured rather than lost.

Activation and paid are intentionally not duplicated here: activation lives in the
retention gate, paid in billing. The conversion gate thresholds are in
[BUILD_STATUS.md](BUILD_STATUS.md).
