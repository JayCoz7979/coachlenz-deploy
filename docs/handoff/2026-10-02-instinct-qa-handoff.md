# Handoff to Instinct — CoachLenz detection hardening

Paste this whole block into instinct to continue the QA campaign. Run the grumpy
40-year-consultant lens (same standard every CGE product gets): no flattery, business
truth first, real evidence not vibes.

## Mission
Get CoachLenz AI video detection to launch-grade **reliability and accuracy**. That is
the #1 priority, it is the trust-maker. Everything else is secondary.

## HARD SAFETY RULES (do not cross, no exceptions)
- **No live outbound.** Never fire Resend email, Stripe, SMS, or webhooks to "test."
- **No real Anthropic COGS to verify.** A full analysis run costs ~$4-13 of Jay's money. Verify from the LOGGED runs (agent_logs), the DB, dry-run, or Quick Test (opening minutes, pennies). Never kick a full re-run just to check something.
- **Production is READ-ONLY.** Do not run signup/CRUD/analysis/write workflows against prod (server-side outbound can't be browser-intercepted). Write/auth/isolation tests run ONLY against a local dry-run stack with outbound keys unset.
- **Do not change** locked pricing, brand colors, or design. Preserve the live app.
- **Branch + PR, never merge without Jay's explicit go.** One fix path per finding, not a menu.
- Verify every finding against real code/data BEFORE "fixing." A fix to a non-bug is worse than none. Do not ship risky/under-tested fixes into the detection money-path.

## Context
- Product: CoachLenz, AI film-analyst OS. FastAPI backend + Next.js frontend, Railway Postgres + Cloudflare R2 (NOT Supabase for app data).
- Backend: `https://coachlenz-backend-production.up.railway.app` (routers at root, no /api prefix).
- Detection engine: `backend/workers/worker_ai_detect.py` (3-pass Claude vision, CODE_VERSION multipass-v28+), ingest+probe `backend/workers/worker_ingest.py`, accuracy engines `backend/services/tendency_engine/` (court_zones.py, basketball_scout.py, players.py, possession_anchor.py).
- Read prod safely via: `railway ssh --service coachlenz-backend python - <<'PY' ... PY` (container has asyncpg + DATABASE_URL; summary_json is Fernet-encrypted, decrypt via backend.services.encryption.decrypt_json).
- QA harness + report: `qa/` (Playwright public + protected read-only specs; write/auth specs gated behind QA_ALLOW_WRITES=1 + local dry-run stack). Append new runs to `qa/QA_REPORT.md`, do not overwrite.

## Already fixed — DO NOT re-flag (confirm still-green instead)
- Detection crashes (PR #258, merged b3679a0): event_type/time_seconds coercion (asyncpg crash), TemporaryDirectory ignore_cleanup_errors (Errno 39), scalar_one_or_none on deleted game, ffprobe -rw_timeout.
- Duration probe (#257): backend/utils/media.duration_from_probe (format OR stream OR tag) + retry + stored-duration fallback + diagnosable error.
- Accuracy (merged this cycle): court_zones taxonomy so wing-3s count + free throws excluded from FG% (#240), honest possession/pace on single-cam (#241), gate shot-recall FGA-only (#242), player grades/tendencies honesty + low_sample flag (#250), run preservation (#239), retention credits F1/F2/F3 (#244/#245/#246).

## Current real state (measured, pre-#258 deploy)
- Detection jobs: 67 done / 12 error = 15% failure. The named causes are now fixed in #258; **re-measure the failure rate after #258 deploys to confirm it dropped.**
- needs_review = 34.8% of plays (1,479/4,251). Honest single-cam uncertainty, but a trust-surface (QA-08).
- Cost: avg $5.87, max $13.23 (vs $13.48 deep ceiling).

## Open backlog to work (detection first)
- QA-10: capture + store video duration at UPLOAD (client-side) so detection never depends on ffprobe-over-R2 for the fallback (durable fix for the #1 historical failure).
- QA-07: event batch insert is all-or-nothing on the money path; add per-row salvage on commit failure so one bad play doesn't nuke a paid run. Needs its own test.
- QA-11: live two-account tenant isolation on a local dry-run stack (qa_user_a vs qa_user_b by direct ID/URL). App-layer org filters only, no DB RLS.
- QA-05: stale `status=analyzing` can block a re-run; self-heal in the trigger.
- QA-08: frame needs-review as "single-camera limit" and calibrate ESCALATION_THRESHOLD once there is coach-correction data.
- Accuracy deep-dive: adversarially re-verify a real logged game's events (made/miss vs scoreboard, possession side, zone mapping) end to end; flag any residual misreads.

## NOT instinct's job (Jay's launch blockers)
- Legal `-draft` COPPA/FERPA text finalized by the attorney, then bump `*_VERSION` in services/legal.py.
- Stripe price IDs set for $9.99 / $29.99 (+ annual) so revenue + the F1 allotment fire.

## Deliverable
Append a dated run to `qa/QA_REPORT.md`: findings ranked Critical..Low, each with full detail block (location, expected vs actual, evidence, root cause); paste-ready fix code for every Critical/High; one-line direction for Medium/Low; a backlog list. Ship fixes on a branch + PR, CI green, and stop — Jay merges. Confirm no live outbound fired and no QA data/users were left behind.
