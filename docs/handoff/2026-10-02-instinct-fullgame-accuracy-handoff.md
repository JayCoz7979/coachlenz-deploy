# Handoff to Instinct — LEAD the full-game detection accuracy proof (QA-13)

Instinct is the QA agent and OWNS this pass. Run the grumpy 40-year-consultant lens: no
flattery, business truth first, real measured numbers not vibes. This is the gate before
CoachLenz does any coach outreach — the free done-for-you breakdowns ARE full-game runs in
front of real coaches, so the current engine's accuracy must be PROVEN first.

## Mission
Measure the CURRENT detection engine (`multipass-v29`) on ONE full game against ground
truth, and return an honest grade + a GO / FIX-FIRST verdict. Detection reliability and
accuracy LOGIC are already fixed (#258–#265); what is unproven is real-world recall/
precision on a full game. Prod check (2026-10-02): 0 of 33 games have ground truth, and
games aren't stamped with the engine version — so there is no existing data to measure.
This pass creates the first real number.

## HARD RULES (do not cross)
- **One authorized COGS run only.** A full deep run costs Jay ~$4–13. Do NOT run anything
  billable except the SINGLE full-game run Jay explicitly authorizes, on a game JAY picks.
  No speculative reruns. Quick Test (opening minutes, pennies) is fine for a smoke check
  but does NOT substitute for the full-game recall number.
- **Ground truth comes from Jay / the film, not the model.** Measure against a game whose
  truth is known (Jay watched it / has the box score), ideally with a visible scoreboard so
  made/miss and score are checkable. The model cannot grade itself.
- Prod is otherwise READ-ONLY. The one authorized run is the only write. Branch + PR for any
  fix; never merge without Jay's go.

## Method (what to measure, and the bar)
Run the full game on the current engine (deep mode). Then measure, honestly:
1. **Play/possession recall** — detected plays vs actual. Basketball shot recall is
   FGA-only (free throws excluded, per the shot-zone taxonomy work). Known single-cam NIGHT
   ceiling is ~68% recall — hold the verdict to what the film can support, don't fake it.
2. **Made/miss precision** — detected shot results vs the scoreboard/known score. This is
   the trust-maker; a wrong made/miss is worse than a miss.
3. **Turnover / steal / block recall** — the events that were historically under-detected.
4. **Label sanity** — zones (wing 3s counted as 3s, not 2s), formations, no phantom
   timeouts, possession/pace honesty on single-cam.
5. **needs-review rate** — how much the engine honestly flags vs asserts.
Set the game's `true_play_count` / `true_shot_count` (admin) and read the detection-quality
gate; combine with a manual spot-check of a sample of plays against the film.

Verdict: a clear GO (accurate enough to put in front of a coach) or FIX-FIRST (with the
specific misses ranked). No "good enough" hand-waving.

## Enabling fix to build alongside (so this is repeatable, not one-off)
- **QA-12: stamp every analysis with its `CODE_VERSION`** (currently not recorded, so we
  can't tell which engine ran which game). Build it so future runs are measurable and a
  pre-engine game can surface a "re-run for current engine" prompt — WITHOUT auto-deleting
  any prior run (run-preservation #239 holds; coach deletes manually).

## Division of labor
Instinct LEADS: defines the bar, drives the measurement, writes the verdict. Claude Code
EXECUTES: runs the single authorized analysis, sets true counts, builds/PRs any fixes
Instinct's findings require, reads the gate/DB numbers back.

## What Jay must provide to start
1. Explicit go to spend the COGS on ONE full-game deep run.
2. The specific game (uploaded, known-truth, scoreboard ideal).

## Deliverable
Append a dated run to `qa/QA_REPORT.md`: the measured numbers (recall, made/miss precision,
turnover recall, needs-review rate), the manual spot-check sample, and the GO / FIX-FIRST
verdict. Ship any fixes on a branch + PR, CI green, Jay merges. Confirm the single run was
the only billable action and no QA data was left behind.
