# Engine §11 (Player One-Pager) & §12 (Heat Maps) — Rescope Against Real Code

**Date:** 2026-07-31 · **Method:** audited against the deployed codebase; where the code contradicts the v3.0 guardrail, the code wins.

Both sections are labeled **STATE 3 — NET NEW** in the v3.0 master prompt. Neither is net-new. §11's export layer and §12's heat maps are already built and shipping. This document corrects each premise and gives a buildable, code-grounded scope.

---

## §11 — Player Layer / One-Pager

### v3.0 said
> "Build `player_one_pager` as a **new `report_type`** … cheat_sheet exists but does not meet this readability standard."

### What's actually true
1. **`report_type` is the wrong axis.** `report_type` is a CHECK-constrained enum: `('opponent','self_scout','custom')` (`migrations/001_initial_schema.sql`). The audience variants (coordinator / head_coach / position / player) are **export formats**, computed on the fly in `services/report_export.py:build_export()` and served by `GET /reports/{id}/export?format=…` (`routers/reports.py:130`). A player one-pager is a **new export format**, not a new report_type. There is no `cheat_sheet` report_type either — that's also v3.0 fiction.
2. **A `player` export format already exists** (`report_export.py:264 _player`) — "Player Bulletins," one block per tracked jersey, reshaped from `summary.player_tendencies.by_player`. It is wired into the export menu (`app/reports/[id]/page.tsx:512`) and rendered by the shared `printDoc()` (`page.tsx:267`).
3. **The existing player format violates the §11 readability standard.** `_player` emits exactly what §11 forbids: percentages and stats (`"21 touches, 4.2 avg, 55% success"`, `page.tsx` `_player_cue`), per-player bulletins rather than one team game-plan page, and no THE KEY / WHO TO WATCH / WHAT THEY RUN / WHAT WE DO structure.

### Requirement-by-requirement

| §11 requirement | Status | Evidence / gap |
|---|---|---|
| Player-facing output exists | **FOUND** | `format=player` bulletins |
| Single print-ready one-pager (not per-player bulletins) | **MISSING** | `_player` returns N blocks, one per jersey |
| THE KEY (what they do + what we do), auto-selected | **MISSING** | no equivalent; source data exists in `summary.scouting.head_coach_priorities` / `game_plan_priorities` |
| WHO TO WATCH (3 jerseys, one phrase each) | **PARTIAL** | `by_player` ranked list exists; needs 6th-grade rewrite, top-3 cap |
| WHAT THEY RUN / WHAT WE DO (plain English) | **PARTIAL** | tendency sections exist; need verb-first, jargon-stripped rewrite |
| No percentages; convert "78%" → "almost always" | **MISSING** | current output is percentage-heavy |
| ≤12-word sentences, 6th-grade, action-verb bullets | **MISSING** | no readability transform anywhere |
| Print-safe layout (14pt/24pt, 1.5 spacing) | **PARTIAL** | `printDoc()` is print-safe but serif/dense; needs a one-pager stylesheet |
| Static heat map embedded | **PARTIAL** | football print map exists (`buildHeatMapHtml`, §12); needs 3-color static player variant |
| FERPA confidentiality line | **CHECK** | verify it's in `printDoc` footer; add if absent |

### Recommended build (§11)
1. **New export format `player_onepager`** in `report_export.py`: add to `EXPORT_FORMATS`, a `_player_onepager(report)` builder returning the fixed one-pager blocks (THE KEY / WHO TO WATCH / WHAT THEY RUN / WHAT WE DO). Do **not** touch `_player` (bulletins stay for coaches who want per-player detail).
2. **THE KEY auto-selection** (pure, testable): pick from `scouting.head_coach_priorities[0]` (football) or `scouting.game_plan_priorities[0]` (basketball); fall back to top personnel mismatch in `player_tendencies`, then to the loudest situational tendency. Always two-part (what they do + what we do).
3. **Readability transform** (pure helper): a `plainify()` that strips percentages to bands ("almost always" ≥75, "usually" 60-74, "sometimes" 40-59), removes jargon via a small term map (ISO→"one-on-one", ICE→"take away the middle"), and clamps sentence length. Unit-test the band + jargon maps like the existing tendency-keys tests.
4. **Dedicated print CSS**: a one-pager branch in `printDoc()` (or a sibling renderer) at 14pt/24pt, 1.5 spacing, single page, with the static 3-color heat map from §12.
5. **Wire into the export menu** (`page.tsx` dropdown) as "Player Game Plan (1 page)".
6. **FERPA line** in the footer if not already present.

**Effort:** medium. All source data exists; the work is a new pure builder + a readability transform + a print stylesheet + menu wiring + tests. No schema change, no model call, no new report_type.

### Open decisions (§11)
- **Team one-pager vs per-player**: §11's template is one team page. Confirm we keep `_player` bulletins AND add the one-pager (recommended), rather than replacing.
- **THE KEY tie-break** when no `scouting` block exists (thin film): fall back to top tendency section, or suppress THE KEY and lead with WHO TO WATCH?

---

## §12 — Heat Maps

### v3.0 said
> "STATE 3 — NET NEW. Build it. If prototype code is committed, wire it to live data."

### What's actually true
Heat maps are **built and rendering from live report data**, on screen and (football) in print:
- **`components/report/FieldHeatMap.tsx`** — football. Pass-target 3×3 field grid (depth × lateral) + behind-LOS strip, run-gap tiles, run-direction bars. Interactive metric toggle (Volume / Success% / Avg Yds). Reads `summary.offense.pass_distribution` / `run_gap_analysis` / `run_direction_analysis`.
- **`components/report/BasketballShotChart.tsx`** — basketball. Per-zone bars, **dual-encoded** (bar length = volume, color = FG% on a red→gold→green ramp), plus Key Players. Reads `summary.shot_zone_map.zones` (`attempts`, `made`, `fg_pct`, `pct_of_all_shots`).
- **Print**: football heat map is rebuilt light-theme for PDF in `app/reports/[id]/page.tsx:209 buildHeatMapHtml()`. Basketball has **no** print heat map. No **player-layer** static 3-color map exists.

So §12 is a "close the gaps + reconcile the metric" job, not a build-from-scratch.

### Map-by-map

| §12 spec | Status | Evidence / gap |
|---|---|---|
| Map 1 — Team shot-zone map, eFG bands (RED ≥55 / ORANGE / YELLOW / GREEN <35) | **PARTIAL** | zones render, but metric is **raw FG%**, not **eFG**, and color is a **continuous ramp**, not the 4 discrete bands. Bars, not a spatial court. |
| Map 1 overlay — attempt frequency + "HIGH attempt + RED = 🚨 priority" | **PARTIAL** | `pct_of_all_shots` shown; no explicit priority-takeaway flag |
| Map 2 — Individual player shot-spot map (top-2 red / bottom-2 green, drive arrow) | **MISSING** | Key Players list exists; no per-player per-zone spots or drive-direction arrow |
| Map 3 — Turnover location map | **MISSING** | turnover counts exist per player; no half-court turnover plot |
| Map 4 — Run/Pass tendency matrix (down × hash × zone → run%) | **MISSING** (different map built) | `FieldHeatMap` shows pass-target field + run gaps, not a run%-by-down/hash matrix. Down/hash data exists on `Event` (`hash_position`, `down`) — the matrix is buildable from events. |
| Map 5 — Field-zone run-direction map (weighted arrows) | **PARTIAL** | run-direction shown as **% bars** (left/right/inside/outside), not spatial arrows |
| Player-layer heat map — static, print-safe, **3 colors**, no numbers, 1 caption | **MISSING** | on-screen maps are multi-color + numeric; football print map is multi-color + numeric |
| "Never RED if confidence LOW; downgrade to YELLOW" | **MISSING / BLOCKED** | per-zone confidence is **not** computed — only game-level `summary.data_confidence.avg_confidence`. This rule needs a per-zone confidence, which the tendency engine does not currently emit. |

### Metric & threshold reconciliation (decide before building)
- **eFG vs FG%.** §12 specifies **eFG% = (FG + 0.5·3P) / FGA** with hard bands. The engine ships **raw `fg_pct`** on a continuous ramp. Either (a) add `efg_pct` to `shot_zone_map.zones` and re-key the color scale, or (b) formally adopt FG% as the shipped metric and drop eFG from the spec. Recommend (a) for correctness — eFG is the right basketball metric — computed in the tendency engine so print and screen share it.
- **Discrete bands vs ramp.** The continuous ramp is arguably better UX for coaches, but §12's Player Layer explicitly needs the **3-color discrete** version. Keep the ramp for the Coach Layer; build a discrete 3-band mapper for the Player Layer.
- **Spatial court vs bars.** Current maps are bar/grid, not a to-scale half-court/field. A true spatial court (Map 1/2/3) is the biggest net-new visual. Decide whether spatial rendering is worth it or whether the honest bar encoding stays.

### Recommended build queue (§12), smallest-first
1. **Add `efg_pct` + per-zone `confidence`** to `shot_zone_map.zones` in the basketball tendency engine (unblocks the eFG bands AND the "never RED if LOW" rule). Pure engine change + tests.
2. **Discrete 3-color Player-Layer mapper** (shared by screen print + the §11 one-pager): a pure function `zone → {red|yellow|green}` honoring the "downgrade RED→YELLOW when confidence LOW" rule. This is the §12↔§11 bridge.
3. **Basketball print heat map** — mirror `buildHeatMapHtml` for shot zones so the PDF carries the shot chart (parity with football).
4. **Priority-takeaway flag** — mark HIGH-attempt + hot-eFG zones with 🚨 in the Coach Layer (cheap, high value).
5. *(Larger, optional)* Map 4 run/pass matrix (buildable from `Event.down` + `hash_position`), Map 3 turnover plot, Map 2 player shot-spots. These are genuinely new visuals; scope each separately if the one-pager doesn't already satisfy the coaching need.

### Open decisions (§12)
- **Adopt eFG (recommended) or keep FG%** as the shipped basketball metric?
- **Per-zone confidence**: add to the engine now (needed for the RED/LOW rule and the honest Player Layer) — confirm.
- **Spatial court rendering**: build true to-scale courts/fields (Maps 1-3), or keep the honest bar/grid encoding and only add the discrete 3-color Player Layer? The bar encoding is defensible; spatial is the expensive path.

---

## Combined build queue (if we proceed)

**Shared foundation (do first):**
- A) Basketball engine: add `efg_pct` + per-zone `confidence` to `shot_zone_map.zones` (+ tests).
- B) Pure `plainify()` readability transform (percent→band, jargon map, sentence clamp) (+ tests).
- C) Pure discrete 3-color zone mapper with the confidence-downgrade rule (+ tests).

**§11:**
- D) `player_onepager` export format using A+B+C; THE KEY auto-selector; one-pager print CSS; menu wiring; FERPA line.

**§12:**
- E) Basketball print heat map (parity with football).
- F) Priority-takeaway 🚨 flag in the Coach Layer.
- G) *(optional, scope separately)* Map 4 matrix, Map 3 turnovers, Map 2 player spots, spatial courts.

## Do NOT
- Add a `player_one_pager` **report_type** or migrate the report schema — it's an export format.
- Rebuild `FieldHeatMap` / `BasketballShotChart` — extend them.
- Replace the `_player` bulletins format — add the one-pager alongside it.
- Assume per-zone confidence exists — it does not yet; the engine must emit it before the "never RED if LOW" rule is honest.
