# CoachLenz Legal Readiness — instinct QA pass (2026-10-02)

Lens: grumpy 40-year consultant. No flattery, business truth first.

## The honest verdict

The **enforcement** is done and now airtight. The **binding legal text for minors'
data is not something I can finalize** — that needs a licensed attorney's eyes, and no
amount of code closes that inch. I did not remove a single "ATTORNEY REVIEW REQUIRED"
banner or flip a version off `-draft`, because doing so would represent attorney-reviewed,
school-signable COPPA/FERPA terms that do not exist. On a platform handling children's
film, that is the one shortcut you do not take.

What I did do: get everything else to the one-inch line, make the drafts **accurate**
(so the attorney reviews truth, not errors), QA the consent enforcement to zero gaps, and
stage activation to a clean, documented switch.

## What this pass fixed (shipped, branch + PR, not merged)

1. **Subprocessor accuracy (HIGH).** The drafts listed **Supabase** as the database host
   and **Twilio** for phone verification. Neither is true: the app runs on **Railway
   PostgreSQL**, and SMS/phone verification was removed (email is the sole identity gate),
   so Twilio receives nothing. A DPA a school signs that names vendors you don't use — and
   omits your real database host — is a factual defect and a trust problem. Corrected in
   `legal/privacy-policy.md`, `legal/data-privacy-agreement.md`, `legal/README.md`.
2. **Cookie policy analytics (MED).** Verified there are no third-party analytics in the
   codebase (no GA/PostHog/etc.). Replaced the `[FILL-IN]` guess with a definitive "no
   analytics cookies" statement in `legal/cookie-policy.md`.
3. **COPPA/FERPA gate on manual play tagging (MED, defense-in-depth).** `POST /events`
   and `POST /events/bulk` wrote student jerseys with only an ownership check. New orgs
   can't reach them without attesting first (game creation is gated), but the guarantee
   was implicit and left a legacy edge. Added the explicit `assert_student_consent` gate
   to both + a regression test proving it blocks when no attestation is on record.

## Consent enforcement — verified coverage (every minors'-data first-touch is gated)

| Entry point | Router | Gate |
|---|---|---|
| Terms + Privacy acceptance | `auth.py` (signup) | recorded per user |
| Game film upload | `games.py`, `ingest.py` | `assert_student_consent` |
| Roster create / import / move | `roster.py` (×3) | `assert_student_consent` |
| Live Game Logger | `live_game.py` | `assert_student_consent` |
| Basketball / football scouting | `scout.py`, `scout_football.py` | `assert_student_consent` |
| Onboarding | `onboarding.py` | `student_data_consent` |
| Manual play tagging | `events.py` (×2) | `assert_student_consent` **(added this pass)** |
| Recruiting profile publish | `recruiting.py` | directory-disclosure attestation |
| Terms/Privacy version bump | `ReconsentGate.tsx` + `/legal/accept-latest` | re-consent modal |

Model: the student-data attestation is **per-org** — once any gated endpoint forces it,
the whole org is cleared. Because every first-touch surface above is gated, **no new org
can store a minor's data without attesting first.** That is the guarantee you want.

## One-step activation (what makes it "live")

When counsel signs off, this is the whole switch:
1. Fill the remaining `[FILL-IN]` fields in `legal/*.md` (see below) and remove the
   "DRAFT — ATTORNEY REVIEW REQUIRED" banners.
2. In `backend/services/legal.py`, change the four version constants from
   `2026-07-31-draft` / `2026-08-05-draft` to finalized dated versions (drop `-draft`).
   That bump **forces every user to re-accept** Terms/Privacy on next load (the
   re-consent modal is already wired) and re-prompts the org attestation.
3. Publish the finalized docs on the public routes (see follow-ups).

Nothing else in code changes. The enforcement already runs at the current `-draft`
versions today.

## Decisions only you / counsel can make (the remaining `[FILL-IN]`s)

- **Effective date** — all docs (set at activation).
- **Arbitration provider + venue** — `terms-of-service.md`: AAA vs JAMS, and the Alabama
  county (Athens is in Limestone County). A legal-venue choice; your call with counsel.
- **DPA signer fields** — `data-privacy-agreement.md` is a per-school template; the school
  fills name/title/date at signing. Leave as-is.
- **Parents' Bill of Rights effective date** — `parents-bill-of-rights.md`.

## Recommended follow-ups (not done this pass — flagged honestly)

- **Public document routes (HIGH before selling to schools).** The `/privacy` and
  `/terms` pages are thin summaries. The full Privacy Policy, DPA, **Parents' Bill of
  Rights** (NY Ed Law §2-d requires it be publicly posted), and Cookie Policy have no
  public route yet. Build routes that render the finalized `legal/*.md`.
- **Parent data-access / deletion request path (HIGH for COPPA).** COPPA gives parents the
  right to review and delete their child's data. There is a `deletion-certificate-template.md`
  but no `/privacy/delete-request` flow wired. Build it before onboarding real minors' data.
- **Manual-tag 403 handling (LOW).** If a legacy org (none at launch) hits the new events
  gate, the game page should surface the attestation modal, not a generic error.

## Bottom line

Enforcement: **done and verified.** Drafts: **accurate and attorney-ready.** Activation:
**one documented switch.** The real remaining dependency is a lawyer reviewing the
minors'-data terms and you making the venue/date calls. I will not fake that step for you —
but everything around it is finished.

Powered by Cosby AI Solutions.
