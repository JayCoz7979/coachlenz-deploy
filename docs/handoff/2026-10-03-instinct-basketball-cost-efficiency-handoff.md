# Handoff to Instinct — LEAD: cut basketball analysis COGS without raising the price

Instinct owns this. Grumpy 40-year-consultant lens: real measured numbers, no vibes.

## Mission (the business goal, in Jay's words)
Find a **cheaper, more efficient way to analyze basketball film** so the per-game cost on
OUR end drops hard — WITHOUT raising the customer's price. The target outcome: a coach/AD
can afford to run analysis on **every game for every team**, not just a few marquee games.
Today basketball is expensive enough that it discourages "analyze everything." Fix that.

## Why basketball is expensive (confirmed cost drivers, 2026-10-03)
- **Model mix is the #1 lever.** `DETECT_MODEL = claude-sonnet-4-6` ($3/$15 per MTok) for
  bulk passes; `VERIFY_MODEL = claude-opus-4-8` ($15/$75 — **5x Sonnet**) for the deep 3rd
  "verify" pass; `GRADE_MODEL = Opus` for the opt-in grade pass. Deep mode = ~3 calls/segment
  with Opus on the verify → that is the bomb.
- **Frame density.** Basketball samples `FRAMES_PER_WINDOW_BB_FAST=120` (~1 frame/2.5s) and
  `BB_DEEP=100` (~1/3s) — far denser than football, because action is continuous. More
  frames → more input tokens → more cost. `FRAMES_PER_BATCH=5`.
- **Segment count.** A 97-min game = ~389 windows. Deep uncapped (`full=true`) analyzes all
  389; a customer run is capped at `MAX_SEGMENTS_PER_RUN=150` (thinned evenly).
- Prompt caching (ephemeral `cache_control`) is already in place (cache read $0.30 vs $3.00
  input for Sonnet — keep maximizing it).

## Hard cost numbers from the 2026-10-03 run (DHHS vs LHS, 97 min, deep)
- My run used `full=true` (uncapped, all 389 segments, deep/Opus) → **$64.21**. This is NOT
  a customer path (the UI never sends `full=true`). Best-case recall, worst-case cost.
- A customer's deep-whole-film is capped at 150/389 segments → est. **~$20–30**.
- **Fast-full basketball cost is UNMEASURED** — that's the default path and the real baseline
  to establish.

## Cost levers to evaluate + build (ranked by expected $ impact)
1. **Adaptive Opus, not blanket.** Run the Opus verify ONLY on the genuinely hard plays
   (low confidence, contradictions — `CONTRADICTION_CONF_CAP` logic already flags these),
   not every segment. If only the bottom ~15% confidence go to Opus, deep cost could drop a
   lot while keeping the tie-breaker value. Biggest single lever.
2. **Skip dead time.** Basketball film is full of free throws, timeouts, inbounds, walk-ups,
   warmups. A cheap pre-pass (ffmpeg scene/motion detection, or a Haiku triage look) to find
   live-action windows and SKIP dead stretches → fewer frames analyzed, same recall.
3. **Cheaper triage model (Haiku 4.5).** A Haiku first look to classify windows (action vs
   dead / shot-likely vs not), then spend Sonnet only on action windows and Opus only on
   ambiguous plays. A cost ladder Haiku → Sonnet → Opus.
4. **Frame efficiency.** Test whether BB fast can hold recall at a lower frames/window (e.g.
   120 → 80) or with smarter (motion-triggered) sampling instead of uniform. Each frame cut
   is linear savings.
5. **Make fast-full the default and GOOD.** Steer basketball to fast-full for the "every
   game" use; reserve deep for on-segment drill-down (already in the UI). If fast-full is
   accurate enough, deep-full is rarely needed.
6. **Batching / caching.** Confirm the big system prompt is cached on every call; test larger
   `FRAMES_PER_BATCH` to amortize per-call overhead within token limits.

Prior work to build on: memory `coachlenz-detection-cost-levers` (Tier 1a score-bug
crop-skip SHIPPED, verify-pass caching done, Tier 2/3 menu incl. deep-on-segment pending).
This mission is Tier 2/3.

## Accuracy re-baseline on the REAL customer path (correct the 2026-10-03 test)
The $64 run was `full=true` (uncapped) = denser than any customer gets, so its 261 plays are
a CEILING, not the coach experience. Re-measure on the DEFAULT path:
- Run **fast-full** on DHHS vs LHS (0c96b094) — cheap (~$3–5), ONE authorized run, Jay's go.
- Measure recall/precision the same way: plausibility (shots/possessions in range), score
  reconstruction vs the film scoreboard if present, and a 12-play spot-check Jay verifies.
- Compare fast-full vs the deep data already on the game. Deliver the accuracy/cost tradeoff:
  what does a coach actually get per dollar on the default path?

## Margin confirmation (price stays fixed — cut COST, not raise price)
- Confirm the capped deep (~$20–30) and the measured fast-full cost against the deep-basketball
  credit price (60 credits) and the **65% margin floor** (`coachlenz-pricing-model`).
- If a path is below floor, the fix is **cost reduction (levers above) or the credit cost of
  the analysis**, NOT the customer's dollar price. The whole point is coaches run everything
  without a price hike.

## HARD RULES
- **One authorized COGS run per test, on a game Jay picks.** No speculative reruns. Iterate
  cheaply with Quick Test (opening minutes, pennies) and deep-on-segment, not full runs.
- Prod READ-ONLY except the single authorized run. Branch + PR for every change; never merge
  without Jay's go. Preserve run-preservation (#239) and the free Live Game Logger behavior.
- Measure every optimization's recall impact — a cheaper run that tanks recall fails the
  mission. Cost AND accuracy, together.

## Division of labor
Instinct LEADS: audits the cost drivers, designs the cheapest path that holds recall, sets
the accuracy/margin bar, writes the verdict. Claude Code EXECUTES: builds the optimizations
as PRs, runs the authorized tests, reports numbers back.

## Deliverable
Append a dated run to `qa/QA_REPORT.md`: measured fast-full cost + accuracy vs deep, the
ranked cost-lever plan with expected $ savings, the margin check, and a GO plan. Ship
optimizations on branches + PRs, CI green, Jay merges. Confirm only the authorized run(s)
were billable.
