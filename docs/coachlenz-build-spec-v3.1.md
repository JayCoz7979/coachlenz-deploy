# CoachLenz Build Spec v3.1 (constants + non-negotiables)

**Supersedes** the "LOCKED PLATFORM CONSTANTS" and "NON-NEGOTIABLES" blocks of the
v3.0 Master Build Prompt. This is the versioned source of truth for the platform
constants so future build sessions audit against the real system, not a stale spec.

**Reconciled against:** `coachlenz-deploy` @ `main` commit `4659b8e` on 2026-07-29;
**guardrail states re-reconciled** against `main` on 2026-07-31 after the v3.0 Engine
build-out (PRs #118, #120, #121, #122, #123, #124). See "§1–§14 Guardrail States".
**Authority:** Team Analysis (Jay + sports analysis consultant + software architect
+ CV/imaging consultant + human movement science consultant).

Why this exists: a v3.0 audit found five "LOCKED CONSTANTS" that contradicted the
deployed code (storage, CV pipeline, backend, auth, sports, pricing, model policy),
plus a self-contradiction (sonnet-only vs. the required Opus verify pass). Building
to the old block would have produced confidently wrong code and a mis-stated legal
DPA. Tags below: **[VERIFIED]** (file:line), **[CORRECTED]** (changed from v3.0),
**[CONFIRM]** (human action, not determinable from this repo).

---

## LOCKED CONSTANTS (corrected)

```
TECH STACK
  Frontend:     Next.js (App Router) in frontend/                    [VERIFIED]
  Mobile:       ROADMAP, not a current constant. No mobile app in    [CORRECTED]
                this repo. Bundle id com.cosbyaisolutions.coachlenz
                applies only once a mobile app exists.
  Backend:      FastAPI + SQLAlchemy (async, asyncpg) on Railway.    [CORRECTED]
                Background jobs via a DB job queue (models/job.py);
                Celery + Redis available. NOT Supabase Edge Functions.
  Database:     Postgres on Supabase (project mbkstodswexxvdgyunio). [VERIFIED ref]
                Access org-scoped in the API layer (organization_id
                filters). Confirm Postgres RLS policies exist for
                defense-in-depth.                                    [CONFIRM RLS]
  Auth:         Custom JWT (PyJWT HS256 signed with SECRET_KEY,      [CORRECTED]
                passlib/bcrypt hashing, refresh tokens).
                NOT Supabase Auth. (backend/services/auth.py:29)
  CV pipeline:  Anthropic Claude multi-pass VISION (frame-sampled).  [CORRECTED]
                NO YOLO11 / ViTPose / Modal.com in the code. Pose
                estimation is NEW roadmap work if wanted, not a
                current constant. (backend/workers/worker_ai_detect.py)
  Storage:      Cloudflare R2 (S3-compatible via boto3), presigned   [CORRECTED]
                URLs, 7-day expiry. NOT AWS S3 / CloudFront.
                (backend/services/r2.py:48 -> *.r2.cloudflarestorage.com)
  Email:        Resend. Prod domain coachlenz.com (config default    [VERIFIED/CONFIRM]
                cosbyaisolutions.com overridden in prod). Founder
                welcome from jay@coachlenz.com.
  Payments:     Stripe (checkout + signed webhook).                  [VERIFIED]
  AI models:    claude-sonnet-4-6 for bulk detection passes;         [CORRECTED]
                claude-opus-4-8 for verify + grade passes only.
                (worker_ai_detect.py:66-67,128). AI is called
                server-side only, never from a client.
  Alert email:  cosbyaisolutions@gmail.com                           [CONFIRM not wired in repo]
  Telegram ops: -5271660549                                          [CONFIRM not wired in repo]
  GitHub:       JayCoz7979/coachlenz-deploy                          [VERIFIED]
  Supabase ref: mbkstodswexxvdgyunio                                 [VERIFIED]

BRAND (web)
  Forest Green:   #2D5016  (rgb 45,80,22, var(--green3))             [VERIFIED]
  Gold:           #C9A84C                                            [VERIFIED]
  Background:     #07090d
  Fonts:          Syne (headings), DM Sans (body), DM Mono (stats)   [VERIFIED partial]
  Footer:         "Powered by Cosby AI Solutions" -> cosbyaisolutions.com  [VERIFIED]
  NO navy. NO blue. No exceptions.

SPORTS
  LIVE (analysis engine exists): 3                                   [CORRECTED]
    American football, flag football, basketball  (sports.py:18)
  ACCEPTED value, NO engine yet (roadmap): volleyball, baseball  (sports.py:20)
  NOT present: soccer, softball
  Public messaging says the 3 live sports, not 7.

PRICING (deployed display rates, pre-launch/founding)               [CORRECTED]
  From the live billing page (frontend/app/settings/billing/page.tsx:10-40),
  labeled "lock in current rates before public launch":
    coach:         $199/mo   |  $1,990/yr
    athletic_dept: $399/mo   |  $3,990/yr
    district:      $1,999/mo |  $19,990/yr
    enterprise:    $14,999   |  contact / custom
  Tier vocabulary (ratified): coach / athletic_dept / district (+ trial, enterprise).
  Entitlement: every PAID tier includes ALL live sports; the trial is single-sport.
    (sports.py TIER_SPORT_LIMITS; guarded by test_tier_billing_coverage.py)
  [CONFIRM] The amount actually CHARGED is set by STRIPE_PRICE_* env vars, not in
    this repo. Confirm each matches the displayed rate in the Stripe dashboard
    before wiring annual/PO billing.
  [CONFIRM] Tier NAMES are shifted by one vs v3.0 (frontend athletic_dept=$399 sits
    where v3.0 said "Program"). Pick ONE naming; apply to Stripe AND marketing.

REPORT SLA + HERO COPY                                              [CONFIRM]
  Not in this repo (marketing site). v3.0's hero "In 60 seconds" and SLA "within 5
  minutes" conflict with each other. Reconcile on the marketing site.

SINGLE CAMERA CONSTRAINT                                            [CORRECTED framing]
  Practical assumption: one fixed camera per game; the UI surfaces "wide
  single-camera angle" as a blind-spot caveat. The engine is frame-sampled Claude
  vision, NOT homography/pose, so v3.0's homography language does not apply.

TEAM ANALYSIS AUTHORITY  (unchanged)
  All gap identification and resolution is authorized by Team Analysis.

UATP v1.3 (mandatory on all analysis runs)                          [VERIFIED]
  Identity disclosure, confidence flagging, live action log, blind-spot honesty,
  auditable cost per run to 6 decimals, no silent failure, no fabricated confidence.
```

---

## NON-NEGOTIABLES (corrected)

1. **Brand:** Forest Green #2D5016, Gold #C9A84C, #07090d. No navy, no blue. [VERIFIED]
2. **Fonts:** Syne (headings), DM Sans (body), DM Mono (stats). [VERIFIED partial]
3. **No placeholder text in any legal document.** Every [BLANK]/[INSERT] is a compliance failure.
4. **No hardcoded credentials.** All secrets via environment variables only.
5. **Student/player data access is org-scoped.** Enforced in the API layer today (organization_id filters); **[CONFIRM]** Postgres RLS policies for defense-in-depth.
6. **EAGLE-EYE** is never "facial recognition", "biometric identification", "faceprint", or "biometric data" in any copy, legal doc, API response, or UI. Use: "jersey number and general appearance grouping, confirmed by coach."
7. **UATP** logs `total_cost_usd` to 6 decimals on every analysis run. No silent failures, no fabricated confidence. [VERIFIED]
8. **Single-camera assumption** holds, but the pipeline is frame-sampled Claude vision, not homography/pose. **[CORRECTED]**
9. **Report SLA:** wording lives on the marketing site and must be internally consistent. **[CONFIRM]**
10. **Pricing** (deployed): coach $199, athletic_dept $399, district $1,999, enterprise $14,999; tiers coach/athletic_dept/district. Confirm Stripe amounts + naming. **[CORRECTED]**
11. **Sports:** 3 live (football, flag football, basketball); volleyball/baseball are roadmap stubs. **[CORRECTED]**
12. **Anthropic API is never called from a client.** Always server-side (worker/backend). [VERIFIED]
13. **AI models:** claude-sonnet-4-6 for bulk passes, claude-opus-4-8 for verify/grade. **[CORRECTED — replaces "sonnet-only", which contradicted the Track 1.2 Opus-verify requirement]**
14. **Footer** on every surface: "Powered by Cosby AI Solutions" -> cosbyaisolutions.com. [VERIFIED]
15. **Never commit directly to main.** Feature branches only, conventional commits.
16. **CGE session standard:** top 20% severity issues per session, actual fix code on every finding.
17. **Team Analysis** is the named authority for all gap findings.

*(v3.0's separate CHANGELOG/TODO/LESSONS/TEST-LOG tracking-file rule is dropped: those files do not exist in this repo and the rule was unenforceable.)*

---

## §1–§14 Guardrail States (reconciled 2026-07-31)

The "AI Analysis Engine — Master System Prompt v3.0" opens every section with a
GUARDRAIL STATE block (STATE 1 = built/skip, STATE 2 = enhance, STATE 3 = net-new).
A 2026-07-31 audit found several of those STATEs wrong, and the Engine build-out
then shipped every genuinely net-new item. **This table is the corrected guardrail
set — the audit wins over the prompt.** Tags: **[BUILT]** shipped this cycle;
**[CORRECTED]** premise was false; **[VERIFIED]** matches code.

| § | v3.0 STATE | Actual | Correction / evidence |
|---|---|---|---|
| §1 Identity & Mission | 2 enhancer | 2 | **[CORRECTED]** Call chain is **FastAPI workers + Anthropic**, NOT "Supabase Edge Functions." Reports run `claude-sonnet-4-6` (config); detection is multi-model (sonnet + opus verify). |
| §2 Evidence Standards | 2 enhancer | 2 | **[CORRECTED]** CV is **Claude multi-pass vision**, NOT "YOLO11 Pose + Modal.com" (that pipeline does not exist). Confidence scoring + sample floors are real. |
| §3 Report Structure | 2 enhancer | 2 | **[CORRECTED]** `report_type` enum is `opponent \| self_scout \| custom` (`migrations/001`). The persona variants (coordinator/head_coach/position/player) are **export FORMATS** (`report_export.py`), NOT report_types. No `cheat_sheet`/`special_teams` report_type exists. |
| §4 Credit Architecture | **1 built** | **[CORRECTED] does not exist** | There is **no credit wallet**. Billing = Stripe subscription tiers (`coach/athletic_dept/district`) + trial game limits + entitlements. The "$9.99/mo + $1/game credits" model and the "0.5-credit re-analysis charge" are fiction; re-analysis is the free `/reports/{id}/retry`. |
| §5 Accuracy Safeguards | 2 enhancer | 2 **[VERIFIED]** | UATP live; single-camera blind-spot honesty surfaced; heat-map sample floors + "never RED on low confidence" enforced in `services/heatmap.py`. |
| §6 Competitive Positioning | 1 prompt-only | 1 | Prompt-level, no code. |
| §7 Output Quality Rules | 2 enhancer | 2 | **[CORRECTED]** "consume credits only after processing" is moot — no credits. Reports generate only from processed events. |
| §8 Sport Expansion | 1 roadmap | 1 **[CORRECTED]** | **3 live** (football, flag_football, basketball), not 7. volleyball/baseball are stubs. See SPORTS above. |
| §9 FERPA Governance | 1 built | 1 **[VERIFIED/partial]** | COPPA/FERPA consent gating live (`services/legal.py`, migration 032). Per-report FERPA notice ships on the player one-pager (`report_export.CONFIDENTIAL_NOTE`); **[CONFIRM]** it also prepends the full coach report output. |
| §10 Non-Negotiable Promise | 2 prompt-only | 2 | Prompt-level self-check. |
| §11 Player One-Pager | **3 net-new** | **[BUILT] #121** | Shipped as a **new export format `player_onepager`** (NOT a new report_type), templated from structured data + `services/plainify.py` enforcement (no LLM). Existing `player` bulletins untouched. |
| §12 Heat Maps | **3 net-new** | **[BUILT, mostly] #121/#122/#123/#124** | eFG% + per-zone confidence on `shot_zone_map`; `services/heatmap.py` bands; Map 1 + priority-takeaway flag; basketball print map; Map 4 run/pass matrix (down×hash); Map 3 turnover **cluster** map (no court plot — single-cam film has no turnover coordinates). **NOT built (deliberate):** Map 2 individual player shot-spots, football spatial player-heat map. |
| §13 AI Coach Chat | **3 net-new** | **[BUILT] #118** | Report-scoped chat on **FastAPI + Anthropic** (NOT "Supabase Edge Function"). Org-isolated, ready-gated, UATP-logged, deterministic no-fabrication fallback. |
| §14 Learning Loop | **3 net-new** | **[BUILT] #120** | Tables `coach_label_corrections`, `account_learning_adjustments`, `label_quality_scores` (migration 034) + Manual Mode. **[CORRECTED]** the "0.5-credit re-analysis charge" and the "expert-labeler global de-identified queue" were NOT built (no credit system; cross-account write collides with the isolation rule). |

**Standing-rules corrections** (in addition to NON-NEGOTIABLES above): STANDING RULE #12 "all AI as claude-sonnet-4-6, no other model strings" is **[CORRECTED]** — detection uses `claude-opus-4-8` for verify/grade. STANDING RULE #11 "always through Supabase Edge Functions or FastAPI" is **[CORRECTED]** — FastAPI workers only, no edge functions. STANDING RULE #10 "7 sports" is **[CORRECTED]** — 3 live.

---

## Downstream track corrections forced by the constants

These are the specific places in the v3.0 tracks that must change to stay consistent
with the corrected constants. Everything else in Tracks 1, 2.1, 2.2, 3, 5, 6, 7
stands as written in v3.0.

- **Track 2.3 (Legal).** Sub-processor lists (ToS, Privacy Policy, DPA) must name
  **Cloudflare R2** for film storage, NOT AWS S3/CloudFront. List **Modal.com only
  if/when** pose estimation ships. Auth is **custom JWT**, not Supabase Auth, if the
  security section describes the auth mechanism. This unblocks legal drafting.
- **Track 2.4 (Deploy safety).** `scripts/deploy_check.sh` in v3.0 targets Vercel;
  deployment is **Railway**. Rewrite the check against Railway (or the actual host)
  before wiring it into CI.
- **Track 4 (Mobile).** Reframe as roadmap: there is no mobile app in this repo yet.
  Its Stripe/S3/Edge-Function references inherit the corrected constants (R2, custom
  JWT, server-side AI) when the app is created.
- **Track 1.2 / NON-NEGOTIABLE #13.** Already reconciled: the Opus verify pass is
  the COGS-metering mechanism and is REQUIRED; the "sonnet-only" rule is removed.

## Open [CONFIRM] items (human decisions, not code)

1. **Stripe charge amounts** vs. the displayed founding rates — verify in the Stripe dashboard.
2. **Tier naming** shift vs. v3.0 — pick one vocabulary, apply to Stripe and marketing.
3. **Report SLA + hero copy** — reconcile the "60 seconds" vs "5 minutes" conflict on the marketing site.
4. **Postgres RLS** policies — confirm they exist for student/player tables (defense-in-depth beyond API-layer scoping).
5. **Telegram/alert-email** routing — not wired in this repo; confirm where P1/P0 alerts actually go.
6. **FERPA per-report notice** — confirmed on the player one-pager; confirm the full coach report output also prepends it (§9).
7. **§12 remaining maps** — Map 2 (individual player shot-spots) and the football spatial player-heat map were deliberately deferred as diminishing-returns; build only on explicit request. See `docs/engine-s11-s12-rescope.md`.

*Re-verify file:line before treating any [VERIFIED] item as final if `main` has moved past `4659b8e` (constants) / the 2026-07-31 guardrail reconciliation.*
