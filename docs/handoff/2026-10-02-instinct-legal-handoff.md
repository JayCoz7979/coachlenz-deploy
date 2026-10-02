# Handoff to Instinct — CoachLenz legal/compliance + launch QA

Paste this whole block into instinct to continue the QA campaign. Run the grumpy
40-year-consultant lens (same standard every CGE product gets): no flattery, business
truth first, real evidence not vibes.

## Mission
CoachLenz is at the launch line. Detection reliability is handled (PRs #258/#259/#260).
Stripe annual pricing is staged (PR #261). This track is the **last compliance item:
COPPA/FERPA + legal consent** for a product that stores MINORS' film and extracts jersey
numbers. Trust is everything in a tight-knit coaching community; a legal or privacy
misstep is existential.

## HARD SAFETY RULES (do not cross)
- **No live outbound.** No Resend/Stripe/SMS/webhooks to "test."
- **No real Anthropic COGS to verify.** Verify from logged runs (agent_logs), the DB,
  dry-run, or Quick Test. Never kick a full re-run.
- **Production is READ-ONLY.** Write/auth/isolation tests only on a local dry-run stack
  with outbound keys unset.
- **Do NOT fake attorney finality.** Never remove a "ATTORNEY REVIEW REQUIRED" banner,
  never flip a `legal/services/legal.py` version off `-draft`, never present AI-written
  minors'-data terms as counsel-approved. That inch is a licensed attorney's. Make the
  drafts accurate and the enforcement airtight; stop there.
- **Branch + PR, never merge without Jay's explicit go.** One fix path per finding.
- Verify every finding against real code/data BEFORE fixing.

## Context
- Product: CoachLenz, AI film-analyst OS. FastAPI backend + Next.js frontend, Railway
  Postgres + Cloudflare R2 (NOT Supabase for app data; Twilio/SMS removed — email is the
  sole identity gate).
- Legal text: `legal/*.md` (attorney-review DRAFTS: terms, privacy, DPA, parents' bill of
  rights, cookie, deletion-certificate). Enforcement scaffolding: `backend/services/legal.py`
  (`DOCUMENT_VERSIONS`, `assert_student_consent`, re-consent helpers). Consent status API:
  `backend/routers/legal.py`. Re-consent UI: `frontend/components/legal/ReconsentGate.tsx`.
- Readiness report (read this first): `docs/legal/legal-readiness-2026-10-02.md`.

## Already done this cycle — DO NOT re-flag (confirm still-green instead)
- Subprocessor accuracy fixed (Supabase/Twilio removed, Railway PostgreSQL named) across
  privacy-policy / DPA / README.
- Cookie-policy analytics placeholder resolved (no analytics in code -> stated so).
- COPPA/FERPA gate added to manual play tagging (`events.py` create + bulk) + regression
  test. Consent now gates EVERY minors'-data first-touch (auth, games, ingest, roster ×3,
  live, scout ×2, onboarding, recruiting, events). Per-org attestation model confirmed.

## Open backlog to work (compliance first)
- **QA-L1 (High): public legal document routes.** `/privacy` + `/terms` are thin
  summaries; the full Privacy Policy, DPA, **Parents' Bill of Rights** (NY Ed Law §2-d
  requires public posting), and Cookie Policy have NO public route. Build routes that
  render the finalized `legal/*.md` (render from a single source of truth, not a 3rd copy).
- **QA-L2 (High): parent data-access + deletion request flow.** COPPA gives parents the
  right to review/delete a child's data. `deletion-certificate-template.md` exists but no
  `/privacy/delete-request` flow is wired. Build request -> ticket -> deletion ->
  auto Deletion Certificate email. (Respect run-preservation/no-auto-delete rules for
  COACH data; this is a distinct parent-initiated PII-erasure path.)
- **QA-L3 (Low): manual-tag 403 UX.** If a legacy org (none at launch) hits the new
  events gate, the game page should surface the attestation modal, not a generic error.
- **Tenant isolation (owner-gated): live two-account test** on a local dry-run stack
  (qa_user_a vs qa_user_b by direct ID/URL). App-layer org filters only, no DB RLS.
- **Detection accuracy deep-dive (owner/COGS): QA-13** — one post-fix full-game run to
  re-measure turnover/overall recall on the current engine (multipass-v29). Jay's COGS call.

## NOT instinct's job (Jay / counsel)
- Attorney review of the minors'-data terms; the venue/arbitration/effective-date
  `[FILL-IN]`s; then the one-step version bump + banner removal that makes legal "live."
- Stripe annual price IDs in the env (PR #261 staged the wiring).

## Deliverable
Append a dated run to `qa/QA_REPORT.md` (findings ranked, full detail blocks, paste-ready
fix code for Critical/High). Ship fixes on a branch + PR, CI green, and stop — Jay merges.
Confirm no live outbound fired and no QA data/users were left behind.
