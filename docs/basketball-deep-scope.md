# Scope: extend deep analysis to basketball

**Goal:** bring basketball up to the same "detailed deep view" depth football has today,
so a basketball game gets multi-pass verification and player grading, not just the single
fast pass. This raises basketball quality toward the football standard and moves its cost
from ~$9/game into the football premium range.

## Where things stand

**Football (deep, today):** a 3-pass engine per batch, football-gated in `_analyze_batch`:
1. Pre-snap pass (Sonnet): segments plays, reads formation/personnel/alignment/tells.
2. Post-snap pass (Sonnet): run/pass, concept, coverage, blitz, result, yards.
3. Verify pass (Opus): adversarially re-checks low-confidence or contradictory plays.
Plus a model-free Reconciler (cross-field contradiction audit), EAGLE EYE jersey reading,
and an opt-in Grade pass (Opus) that grades OL/DL/QB/tackle/coverage technique per jersey.

**Basketball (today):** a single Sonnet pass (`DETECTION_PROMPT_BASKETBALL`) that already
extracts a rich event set into `extra_data` (shot_zone, shot_type, offensive_set,
defensive_scheme, press_type, screen action, transition, paint_touch, kick_out, assist,
inbound plays, etc.) and feeds the six-category basketball scout engine (`scout.py`). It
does NOT run verify, reconcile, or grade. Measured full-game cost ~$9 (219 events on a real
game). The multipass engine, the Reconciler, and the Grade pass are all gated to
football/flag_football, so basketball cannot go deep even if `mode=deep` is requested.

## What is reusable vs new

The deep ARCHITECTURE is sport-agnostic and already built: the batch orchestration, the
merge-by-index, confidence math, the Opus verify loop, frame caching, per-run cost
reporting, human-escalation, and DRY_RUN. Extending to basketball is mostly PROMPTS, FIELD
VOCABULARIES, and RECONCILER RULES, plus flipping the sport gates. It is not a rebuild.

## The work, phased

**Phase 1 - Basketball multi-pass detection.**
- A basketball "set" pass (analog of pre-snap): segment POSSESSIONS and read the setup -
  offensive set (motion, horns, spread, 5-out), defensive scheme (man/zone/press), on-ball
  screen action being initiated, personnel. This is the hardest part (see Risks).
- A basketball "action + result" pass (analog of post-snap): shot zone/type/made-missed,
  assist, drive, ball-screen coverage (hedge/switch/drop), turnover cause, transition,
  paint touch, kick-out. Much of this already lives in the single-pass prompt; refactor it
  into a post-pass anchored to the set pass by possession index.
- Add a parallel basketball multipass path in `_analyze_batch` (not just flipping the
  football gate - basketball needs its own two prompts, not the football pre/post prompts).

**Phase 2 - Verify + Reconciler for basketball.**
- Basketball `VERIFY_KEYS` + a verify prompt tuned to basketball fields (shot zone,
  made/missed, offensive set, defensive scheme). Reuses the existing Opus verify loop and
  frame caching unchanged.
- Basketball `_reconcile` rules, e.g. "made 3 but shot_zone=paint", "zone defense but a
  man-only ball-screen coverage named", "transition possession but a half-court set named".

**Phase 3 - Basketball grading (the player grade board).**
- `GRADE_PROMPT_BASKETBALL`: shot selection, decision-making / passing reads, on-ball
  defense and close-outs, screen quality, box-out / effort, tied to jersey. Analog of the
  football technique grade.
- Un-gate `_grade_plays` for basketball; reuse the high-res jersey-style frame extraction.
  Note basketball jerseys are already handled (legal 0-5 digit scrub exists).

**Phase 4 - Consumers.**
- The basketball scout engine already consumes events; new deep fields flow through
  `extra_data` and DEEP_FIELDS with no schema change. The (currently football-only) Player
  Grades board lights up for basketball once grades are written.

## Risks and hard parts

- **Possession segmentation is the real risk.** Football has discrete snaps (clean play
  boundaries); basketball is continuous, so finding possession boundaries is fuzzier. The
  single pass already segments events at some level (219 on a real game), so it is not
  starting from zero, but the multi-pass depends on stable possession indices to anchor the
  action pass, and that needs validation.
- **Man vs zone and ball-screen coverage are genuinely hard reads** from a single camera and
  will lean on the verify pass more than football's structural reads do.
- **Grading is angle-dependent.** Shot form and defensive stance need a usable view; wide
  broadcast or high baseline angles limit it, same ceiling as football.
- **Film quality still drives cost.** Blurry film means low confidence means more Opus
  verify. Basketball deep should be validated on HD single-camera film. We already have real
  basketball games in the system (DHHS vs LHS, the CTN games) to validate on.

## Cost and quality impact

Basketball deep would move from ~$9/game (fast) into the football range, roughly $20 to $40
depending on verify frequency and whether grading is on, with the same optimizations
(frame-cache, verify-on-Sonnet, HD film) applying. So basketball deep is a premium tier,
priced like football deep+grade, not a free upgrade.

## Effort (relative)

- Phase 1 basketball two-pass prompts + wiring: **M** (prompt engineering is the bulk).
- Phase 2 verify keys + reconciler rules: **S**.
- Phase 3 basketball grade prompt + un-gate: **M**.
- Phase 4 consumers: **S** (mostly free; fields flow through).
- Validation on real HD basketball film: **M** (the make-or-break step).

## Recommendation

Sequence it as: Phase 1 + 2 first (deep detection + verify + reconcile) and validate on a
real basketball game to confirm possession segmentation and read quality hold. Only then add
Phase 3 grading, which is the most angle-sensitive and the most expensive. Do not un-gate
basketball deep in production until it is validated, exactly as we treated the football
grade pass (opt-in behind a flag first). The single biggest de-risker is a clean HD
single-camera basketball game to validate on, which we already have candidates for.
