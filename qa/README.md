# CoachLenz QA harness

Standing end-to-end regression gate. The full report is in `QA_REPORT.md` (appended per run).

## Safety model (read before running)
Production has **live** server-side outbound (Resend email, Stripe, Anthropic vision COGS).
Browser request interception only stops requests the browser makes; it cannot stop
email/SMS/payments/webhooks the server sends. Therefore:

- **Public / read-only specs** (`public.spec.ts`) are safe against any target. They block
  every non-GET request as a belt-and-suspenders and only assert page health.
- **Write / auth / isolation specs** must run ONLY against a **local dry-run stack**
  (backend with the dry-run/freeze flag on and every outbound provider key unset).
  Never run them against production. They are skipped unless `QA_ALLOW_WRITES=1`.

## Run
```bash
cd qa
npm i -D @playwright/test
npx playwright install chromium
# Public smoke against a target (defaults to the local dev server):
QA_BASE_URL=https://app.coachlenz.com npx playwright test public.spec.ts
# Write/auth/isolation suite (local dry-run stack only):
QA_BASE_URL=http://localhost:3000 QA_ALLOW_WRITES=1 npx playwright test
```

## What to add next (QA-11)
A `isolation.spec.ts` that logs in two disposable users and confirms `qa_user_b`
cannot read/edit/delete `qa_user_a` records by direct ID/URL. Gated behind
`QA_ALLOW_WRITES=1` + a local dry-run stack, per the safety model above.
