# Handoff to Instinct — QA the COPPA/FERPA deletion flow

Run the grumpy 40-year-consultant lens. This one is HIGH stakes: a public, unauthenticated
intake that leads to DESTRUCTIVE deletion of a minor's data. If this flow deletes the wrong
kid's data, lets an unauthorized person trigger a deletion, or injects into an inbox, that's
a lawsuit and a trust collapse. Pressure-test it like it's going in front of a regulator.

## What to QA (built in PR #264 — review the code + run write tests on a LOCAL dry-run stack)
Backend: `backend/routers/privacy.py`, `backend/services/privacy_requests.py` (execute_deletion
+ render_certificate), `backend/models/privacy_request.py`, migration `054_privacy_requests.sql`,
emails in `backend/services/email_service.py`. Frontend: `frontend/app/privacy/delete-request/page.tsx`
(public form), `frontend/app/admin/privacy-requests/page.tsx` (admin), sidebar entry.

Flow: public `POST /privacy/requests` -> admin `verify` (attach org) -> admin `fulfill`
(deletion runs the scoped erasure + emails a certificate) / `reject`. Status is token-gated.

## HARD SAFETY RULES (do not cross)
- **No live outbound, no COGS, prod READ-ONLY.** This flow DELETES data and SENDS emails —
  never run a real fulfillment against prod. Write/destructive tests ONLY on a local dry-run
  stack with Resend/all outbound keys unset. Against prod, limit to read-only route-existence
  probes (GET -> 405, unauth admin -> 403); never submit a real request or run a deletion.
- Branch + PR, never merge without Jay's go. Verify every finding against real code first.

## Already handled this build — confirm, don't re-flag
- Admin endpoints are `require_admin`; public status is `secrets.compare_digest` token-gated;
  intake is rate-limited (5/min).
- execute_deletion is ORG-SCOPED on every query and narrow: deletes the specific RosterPlayer
  and de-identifies ONLY that jersey on that player's TEAM games (plays kept). Whole-film
  deletion only for admin-passed game_ids. Tests cover scope + no-op on unknown player.
- HTML-injection: every requester-supplied field is `html.escape`d into the admin email +
  certificate (test proves it).

## Hunt these (the real risks)
1. **Authorization / IDOR.** Can anyone reach an admin verify/fulfill/reject without
   admin_level? Can the status token be guessed/enumerated or omitted? Does a malformed
   request_id 500 (should 404)?
2. **Deletion over-reach / cross-tenant.** Can a fulfill touch data outside the resolved org?
   What if the admin pastes a roster_player_id from ANOTHER org (it should no-op, not delete)?
   Confirm the org scope holds for both roster_player_ids AND game_ids. Jersey reuse across
   seasons: prove a different season/team's same jersey is NOT scrubbed.
3. **Identity verification strength.** The flow leans on human admin verification "in
   coordination with the school." Assess whether that is defensible for COPPA/FERPA and
   document the gap if not (e.g., no automated proof the requester is the parent). This is the
   weakest point — call it honestly.
4. **Destructive-action safety.** No undo on fulfillment. Should there be a confirm step /
   dry-run preview showing exactly what WILL be deleted before it runs? (Currently the admin
   pastes IDs blind.) Propose a preview endpoint if warranted.
5. **Abuse of the public intake.** Rate-limit bypass, spam, oversized fields, injection in
   every free-text field (re-verify escaping end to end, incl. the frontend render).
6. **Data-rule compliance.** Confirm this never collides with coach run-preservation (#239):
   a parent erasure is deliberate, but it must not be reachable as an accidental coach action.

## Still-open backlog (from the prior legal handoff)
- QA-L1: public routes for the full Privacy/DPA/Parents' Bill of Rights (NY §2-d) — the text
  is still attorney-draft, so the rendering infra can be built but must not publish the
  "DO NOT PUBLISH" drafts until counsel finalizes.
- Tenant isolation live two-account test (local dry-run stack).
- QA-13 detection recall re-measure (owner/COGS).

## Deliverable
Append a dated run to `qa/QA_REPORT.md` (findings ranked, full detail, paste-ready fixes for
Critical/High). Ship fixes on a branch + PR, CI green, stop — Jay merges. Confirm no live
outbound fired, no real deletions ran against prod, and no QA data/users were left behind.
