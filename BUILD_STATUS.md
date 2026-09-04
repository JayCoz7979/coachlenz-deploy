# BUILD_STATUS

## Phase: Traffic Proof (CGE standard)

Status: COMPLETE for this run, scoped deliberately. Confirmed with the founder: build
only the traffic-GENERATING slice now (attribution, one free-tool lead magnet, the SEO
foundation), and skip the parts that are dormant with ~0 users (in-product referral, a
content production system, marketplace presence). A prompt does not create traffic; the
publishing and outreach motion is the founder's. Building stops after this so that
motion can begin.

### Channel attribution (built this run)

Extends the conversion funnel from the previous phase. Migration 046 adds
`funnel_events.source` and `organizations.signup_source`.

- Source is a coarse channel label captured on the first visit: a `utm_source`, else
  the referrer host, else `direct` (`lib/funnel.ts` `getSource`, persisted per visitor).
- It rides every beacon event, and is captured on the org at registration
  (`organizations.signup_source`) so the server-emitted `signup_start` and
  `signup_complete` are attributed too. The org carrying the source is also the link
  that lets retention later be read per channel (qualified traffic).
- `services/funnel.build_funnel` now returns a per-channel breakdown (visitors,
  signups, visitor-to-signup, gate), best channel first. Shown in Admin -> Funnel
  under "By channel". Tested in `backend/tests/test_funnel.py`.

### Free tool / lead magnet (built this run)

A genuinely useful, no-signup-required calculator that targets the core pain and ranks
for it, capturing intent from the right visitor.

- Public page `/tools/film-time-saved`: a coach enters games per season and hours per
  manual breakdown and sees the season hours it costs them, framed honestly (no
  invented savings percentage). Server component carries its own SEO metadata; the
  interactive part is a client child.
- It is a top-of-funnel entry: it emits `landing_view` (attributed by source), offers
  the primary CTA to start the trial, and captures a lead email via `POST /leads`.

### SEO foundation (built this run)

- `app/layout.tsx`: `metadataBase`, a title template, Open Graph and Twitter defaults,
  and a `SoftwareApplication` JSON-LD block (honest, no fabricated ratings).
- `app/sitemap.ts` (public pages only) and `app/robots.ts` (authed app disallowed,
  sitemap referenced), both driven by `NEXT_PUBLIC_SITE_URL` (defaults to the app URL).
- Per-page metadata on the new tool page with a canonical.

Deferred by design: in-product referral (no users to refer yet), a content production
system (that is the founder's publishing motion, not scaffolding to pre-build), and
marketplace presence (depends on a chosen ecosystem).

---

## CHANNEL GATE

Prove one channel before adding another, and do not scale paid ads at a low entry
price. A channel counts only when its QUALIFIED traffic, visitors who convert and then
retain, clears the bar at acceptable cost.

- **Primary channel to prove first:** SEO and content (owned/earned, near-zero cost,
  fits a search-driven pain). Its assets this run: the SEO foundation and the
  `/tools/film-time-saved` intent page.
- **Qualified-traffic metric:** per channel, visitor -> completed signup (read in Admin
  -> Funnel, "By channel"), and then whether those signups clear the retention gate
  (the org carries `signup_source`, so retention can be read per channel).
- **PASS bar:** a channel clears the conversion gate on its own traffic (visitor ->
  completed signup >= 5%) AND its signups clear the retention gate, at a cost per
  qualified signup you accept (for owned/earned, effectively time not dollars).
- **STOP line:** a channel below the conversion stop line (< 2%) on a fair sample, or
  that produces no retained users, is dropped rather than scaled.
- **Discipline:** one channel at a time. Prove it downstream (conversion + retention)
  before building or scaling a second. Raw sessions are a vanity number.

### Current reading

Empty, because there is ~0 traffic yet. Attribution, the SEO foundation, and the lead
magnet are live and will attribute the first real visitors by channel. The traffic
motion (publishing, outreach, getting coaches to the tool and the trial) is the
founder's and is the actual next step.

---

## Phase: Conversion Proof (CGE standard)

Status: COMPLETE for this run. Scope confirmed with the founder before code:
instrument the funnel and fix the obvious leaks now, defer the A/B harness and
leak-finding until real traffic exists (both are blind with ~0 traffic today).

### The funnel, as it exists

`/` (landing) -> Start free trial -> `/onboarding` (register -> verify email -> lock
sport) -> dashboard -> first analysis (activation) -> subscribe (paid). A logged-out
visitor lands straight on the register form, so the primary path is not a dead end.
This chains with the retention gate: conversion covers visitor to completed signup,
retention takes it from activation onward.

### Funnel instrumentation (built this run)

First-party only, no third-party trackers, no PII. New `funnel_events` table
(migration 045) plus `services/funnel.py`:

- Anonymous top-of-funnel steps captured via a public beacon (`POST /funnel/event`,
  rate limited, event allowlist): `landing_view`, `cta_click`, `signup_view`. Counted
  by DISTINCT anon_id (a random localStorage id) so refreshes do not inflate visitors.
- Signup steps emitted server-side so they cannot be spoofed: `signup_start`
  (`/auth/register`) and `signup_complete` (`/onboarding` sport lock). Best-effort,
  never blocks signup.
- `GET /admin/funnel` (require_admin, founder-readable) + Admin "Funnel" tab: step
  counts, step-to-step conversion, the single biggest drop-off named with a number,
  and the gate verdict.
- Activation and paid are NOT rebuilt here: the retention gate already has activation,
  billing has paid. This run measures the conversion half only.
- Tests: `backend/tests/test_funnel.py` (dedup, window, biggest drop, gate bands,
  empty state, tz-aware). Logic exercised directly and passing; full suite in CI.

### Conversion hygiene (built this run, copy/structure only, design preserved)

- Hero rewritten to lead with the core pain (time lost to film breakdown) and pass the
  five-second test. `frontend/app/page.tsx`.
- One primary CTA ("Start your free trial"). The competing header + hero "Sign in"
  buttons were demoted to a single quiet header text link.
- Objections handled inline, honest answers only (price, works-on-your-film,
  data safety/COPPA-FERPA, time to value).
- Honest proof only: 14-day free trial, no credit card to start, cancel any time, data
  stays yours. No invented testimonials, logos, counts, or ratings.
- Value anchored against the real cost (a coach's evening), not a price in a vacuum.
- Lead capture for non-converters: `marketing_leads` table + `POST /leads` +
  a landing email form, so a visitor who does not sign up is not lost.

Deferred by design until traffic exists: the A/B harness (nothing to test against yet)
and naming the biggest leak from real data.

---

## CONVERSION GATE

Do not scale paid traffic or ad spend until the funnel clears this gate on existing
traffic. A leaky funnel scaled just loses money faster. Fix the single biggest leak
first, prove the lift, then move on.

- **Primary conversion metric:** visitor -> completed signup (a `signup_complete` per
  unique `landing_view` visitor), over a 30-day window.
- **PASS bar:** >= **5%** visitor-to-completed-signup.
- **STOP line:** < **2%** -> halt any paid traffic and fix the funnel.
- **WATCH band:** 2% to 5% -> keep fixing the funnel, hold spend.

Read it live at Admin -> Funnel. Thresholds live in `backend/services/funnel.py`
(`CONVERSION_BAR`, `STOP_LINE`); change them there and here together.

### Current reading

Empty, because the funnel was not instrumented until now and there is ~0 traffic. The
instrument is live and will populate as visitors arrive. The real bottleneck remains
distribution, not the funnel.

---

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
