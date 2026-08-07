# Changelog

All notable changes to CoachLenz. Newest first. PR numbers link the full diff.

## 2026-08-04 → 2026-08-06 — Security, reliability & controls sprint

A full adversarial audit of the backend (24 findings across billing, auth/tenant
isolation, the analysis pipeline, and FERPA/consent), followed by the two deferred
items, a rate-limiter hardening, a runtime feature-flag control panel, and a UI
confirm-dialog fix. Every change shipped with tests and was verified live in
production.

### Security & financial controls
- **Referral payout is now exactly-once** — the commission credit used a Stripe
  idempotency key so a worker crash/retry can no longer double-pay the referrer.
  (#177)
- **Trial game cap race closed** — uploads reserve a trial slot with an atomic
  conditional UPDATE, so concurrent uploads can't exceed the 1-film trial. (#177)
- **Per-coach monthly analysis cap race closed** — the count+insert is serialized
  with a row lock, so parallel deep runs can't blow past the cap. (#177)
- **Previews no longer burn a credit** — `dry_run`/`test` detections don't record
  billable usage. (#177)
- **Refund on failed analysis** — a run that errors or dead-letters reverses the
  coach's usage charge (usage rows now linked to their job). Always on. (#189)
- **Duplicate-run guardrail** — a 2nd billable analysis on already-analyzed film
  requires confirmation and notifies all team coaches. Flag: `rerun_confirmation`.
  (#189)
- **Duplicate-subscription guard** — `/checkout` returns 409 for an org that
  already has a live subscription, preventing orphaned double-billing. (#178)
- **Cancellation no longer regrants a trial** — `customer.subscription.deleted`
  sets `is_trial=false`. (#178)
- **Rate limiting**: derives the real client IP behind Railway's proxy (per-IP
  limits no longer collapse to one global bucket) (#177), and now uses a **shared
  Redis store** so limits hold across all workers instead of per-process (#180).
- **SMS toll-fraud brake** — `/auth/send-phone-code` has a per-user cooldown +
  daily cap. (#177)

### Compliance & privacy (FERPA/COPPA)
- **Public shared reports no longer leak the coach's raw title** (which could
  contain a minor's name); a neutral derived title is served instead. (#177)
- **Recruiting disclosure consent** — minting a public recruiting link requires a
  per-player directory-disclosure attestation, distinct from the data-collection
  consent. Flag: `recruiting_consent`. (#189, #178)
- **Recruiting scout sends are audited** and fail honestly (502) instead of a
  false "sent" confirmation. (#177)
- **CSV roster re-upload coalesces** instead of NULLing existing student fields.
  (#177)

### Reliability — analysis pipeline & workers
- **Ingest no longer freezes the event loop** — yt-dlp and ffprobe run off-loop,
  so long downloads can't stall heartbeats or the co-located detection worker.
  (#177)
- **Anthropic clients are closed** (`async with`) instead of leaking one per batch,
  and vision calls have an explicit timeout + retry cap. (#177, #178)
- **Detection token budget raised** and truncation is logged, so a dense window no
  longer silently drops all its plays; empty/refusal responses degrade safely
  instead of dropping the segment. (#177, #178)

### Data integrity
- `add_player` returns a clean 409 (not a 500) on the unique-constraint race and
  filters by org; `clone_roster` copies height/weight; `legal_acceptances` gained a
  uniqueness constraint. (#178)
- Batch writes verify parent ownership; prod CORS drops the localhost dev origin;
  the local-file fallback endpoints fail closed. (#178)

### Infrastructure & admin
- **Runtime feature-flag control panel** — Admin → Feature Toggles. Flags default
  to their env var and are overridable by a DB row read at request time (~20s
  propagation, no redeploy; degrades to the env default on any DB error). (#190)

### UI
- **In-app confirmation modal** replaces native `window.confirm()` for every
  destructive action (org/report/film delete, roster/staff/recruiting changes, and
  the duplicate-run prompt). Native dialogs are auto-suppressed in embedded/preview
  panes, which made those buttons silently no-op; the DOM modal works everywhere.
  (#191, #192)

### Migrations
`039` phone-verify throttle · `040` legal_acceptance uniqueness · `042`
analysis_usage.job_id · `043` recruiting-consent columns · `044` feature_flags.
All idempotent, applied via the pre-deploy command.

### Feature flags (Admin → Feature Toggles)
- `rerun_confirmation` — duplicate-run confirmation + team notification. **On.**
- `recruiting_consent` — recruiting disclosure-consent gate. **Off** (pending the
  attorney finalizing the attestation text; bump `RECRUITING_DIRECTORY_VERSION`).
