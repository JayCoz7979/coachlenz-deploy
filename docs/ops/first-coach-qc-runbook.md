# First-Coach QC Runbook — your eyes are the accuracy gate

Until detection accuracy is PROVEN on 2–3 real coach games against the film, **no AI
breakdown reaches a coach without a human QC pass.** This is the controlled first-customer
motion: it doubles as the accuracy validation we never got (no ground-truth game) and the
distribution motion (free, founder-delivered breakdowns).

Current prod detection config (set 2026-10-04): BB fast frames = **120** (dense/accurate),
dead-time skip = **on** (validated-safe), fast made/miss verify = **off** (failed, abandoned);
the made/miss paint prompt fix is live. Cost cuts (frames-80) are deferred until accuracy is
proven — accuracy over cost for the first impression.

## The flow (per free breakdown)
1. **Coach says yes** (from the outreach kit) and sends ONE game — a Hudl link or file.
2. **Run it.** Claude Code runs the analysis on the game (fast-full for the first look;
   deep-on-segment for any stretch that needs more). Report back: cost, play/shot/possession
   counts, needs-review rate, and a 12-play spot-check list with timestamps.
3. **QC against the film (Jay).** Walk the checklist below. Scrub to the spot-check
   timestamps and confirm the engine read them right — ESPECIALLY made/miss in the paint.
4. **Pass or fix.**
   - PASS -> generate the coach-facing report and send it.
   - FAIL -> fix first: re-run denser / deep-on-segment on the weak stretch, or correct the
     bad plays in the Play Log, then re-QC. Never send a breakdown you would not stake your
     name on.
5. **Capture feedback.** Note what the coach says and anything QC caught, so we know whether
   the base engine is analyst-grade before relaxing the gate.

## The accuracy QC checklist (the gate)
Per breakdown, confirm:
- [ ] **Play count is plausible** — a full HS game is ~100–160 field-goal attempts combined,
      ~120–140 possessions. A result far under that = under-detection; re-run denser.
- [ ] **Made/miss is right — check the PAINT first.** This was the known failure (2-of-28
      made). Scrub 4–6 paint/rim attempts: are makes called "Made," not defaulted to
      "Missed"? Paint should convert ~55–65%, not single digits.
- [ ] **Score reconstructs sanely** — made 2s/3s/FTs should roughly rebuild the game's
      score. Wildly low = missed makes.
- [ ] **No phantom events** — timeouts (a handful max per game, not dozens), no fouls on
      ordinary contact, no turnovers on normal made-basket possession changes.
- [ ] **Zones read right** — wing 3s counted as 3s, free throws not polluting FG%.
- [ ] **needs-review items are surfaced honestly** to the coach, not hidden or asserted as
      fact (single-cam limits are a feature of trust, not something to paper over).

## Roles
- **Claude Code:** runs each analysis, reports the numbers + the spot-check list, fixes on
  request (re-run / deep-on-segment / Play Log corrections), generates the final report.
- **Jay:** the accuracy gate — QC against the film, approve or send back, and decide when the
  base engine has earned trust.

## Exit criteria (when to relax the gate)
After **2–3 real coach games pass QC clean** (made/miss solid, counts plausible, no phantom
events), detection accuracy is proven on real film. Then:
- Re-enable the cost cuts (frames-80) and re-confirm on one game.
- Move from "QC every breakdown" to spot-check sampling.
- Open up beyond founder-delivered.

Until then: every breakdown gets your eyes. Reputation is the whole game with a tight-knit
coaching community — we earn the open launch by proving the film reads right, one real game
at a time.

Powered by Cosby AI Solutions.
