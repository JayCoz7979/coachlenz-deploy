# BUILD_STATUS

## Phase: Retention Proof (CGE standard)

Status: COMPLETE for this run. Scope was telemetry and gate only, confirmed with the
founder before any code was written.

### Why the scope was narrowed

CoachLenz is a mature product, not a pre-breadth one. The Retention Proof prompt asks
to build onboarding to first value, the core value delivery, and the learning loop.
An entry-gate read of the repo found all three already built and in production:

- **Onboarding to first value:** `backend/routers/onboarding.py`, `services/trial.py`,
  email identity gate, tier-bound sport lock (migration 018/020).
- **Core value delivery:** film ingest to R2 (`routers/ingest.py`, `upload.py`,
  `workers/worker_ingest`), 3-pass Claude vision detection (`routers/ai_detect.py`,
  `workers/worker_ai_detect.py`), report generation (`workers/worker_reports`,
  `services/report_writer.py`).
- **Learning loop:** migration 034, `services/learning_loop.py`, `routers/learning.py`
  (per-account label corrections roll into account adjustments a coach accepts).

Rebuilding any of these would violate the standing rule "build on the existing backend,
do not rebuild what exists." The genuine gap was the fourth item, retention telemetry
per cohort, and the written gate. That is what this run delivered.

### The core value moment

A coach uploads or ingests a game's film and gets back an AI film-analysis report they
act on. The recurring habit that must retain is analyzing each new game's film. There
is no cold-state delivery: an analysis is always bound to a specific ingested film for
a specific game, so the "never deliver the core moment off an empty state" rule holds by
construction.

### The learning loop (existing)

Coach edits to AI-tagged plays are recorded as label corrections; systematic corrections
become per-account adjustments the coach accepts, which relabel matching plays in future
reports. Org-scoped, no credits consumed. See migration 034 and `services/learning_loop.py`.

### Retention telemetry (built this run)

Derived, not a new table. The authoritative core-action event already exists:
`analysis_usage` writes one row per analysis run and the detection worker DELETES that
row when a run fails or dead-letters, so a surviving row is a delivered analysis. A
duplicate telemetry table would risk drift and fabricated data, so retention is computed
directly from `organizations.created_at` (the cohort) and `analysis_usage.created_at`
(the delivered core actions).

- `backend/services/retention.py`: pure, unit-tested. Cohort = ISO signup week.
  Activation = share of a cohort with a first analysis within 7 days. Return = share of
  a cohort with a second analysis within 30 days.
- `GET /admin/retention` (`routers/admin.py`, gated by `require_admin`, founder-readable):
  per-cohort activation and return plus a matured-cohorts summary and the gate verdict.
- Admin panel "Retention" tab (`frontend/app/admin/page.tsx`): summary tiles, gate
  badges, and a per-cohort table. Inherits existing design tokens, no styling changes.
- Tests: `backend/tests/test_retention.py` (thresholds, activation and return windows,
  maturation, empty state, tz-aware timestamps). Logic exercised directly and passing;
  full pytest runs in CI.

Kept separate from the Athletic Dept usage dashboard (`routers/ad.py`): same events, a
different question. Retention answers "does the core retain?", not "who used how much?".

---

## RETENTION GATE

Do not build feature breadth in CoachLenz until a live cohort clears this gate, or the
core has been iterated until it does. Feature work before the core retains is how good
products die polished.

- **Primary return metric:** share of a signup-week cohort that runs a SECOND film
  analysis within 30 days of signup.
- **Primary action metric:** share of a signup-week cohort that runs its FIRST film
  analysis within 7 days of signup (activation, the leading indicator).
- **PASS bar:** return rate >= **40%** on matured cohorts. Above this, breadth is allowed.
- **STOP line:** return rate < **20%** on matured cohorts. Below this, HALT breadth and
  fix the core.
- **WATCH band:** 20% to 40%. Keep iterating the core, hold breadth.
- **Maturation rule:** a cohort counts toward the verdict only after every member's
  30-day return window has closed. In-window cohorts show as "maturing" and never trip
  the stop line.

Read the live numbers at Admin -> Retention. Thresholds live in
`backend/services/retention.py` (`RETURN_BAR`, `STOP_LINE`, window constants); change
them there and here together.

### Current reading

No cohort has cleared the gate yet because retention was not instrumented until now. The
gate is live and will populate as coaches sign up and analyze film. Until a matured
cohort clears 40%, no new feature breadth in CoachLenz.
