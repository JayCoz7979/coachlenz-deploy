# Live Game Play Logger

Real-time, sideline play-by-play charting for a live game (Football, Flag Football,
Basketball), with a **halftime** and a **full-game** report generated from the logged
plays. New, self-contained module — no existing page, style, route, or table was
modified (only additive files + two additive migrations).

## Architecture (reuses the existing pipeline)

| Concern            | Reuses                                                              |
|--------------------|--------------------------------------------------------------------|
| Session            | `games` row, `status='live'` (migration 038)                       |
| Setup + rosters    | one `game_meta` event (`side='meta'`), like the proven `scout_meta`|
| Plays              | shared `events` table (`event_type='play'`, `side`, `extra_data`)  |
| Reports            | `Job` → `worker_reports` → `live_game_report` → `/reports/[id]`     |
| Report type        | `live_game` (dispatches to the bespoke 9-section writer)           |
| Halftime scoping   | `tendency_reports.params.event_filter` (migration 037)             |

**Side mapping** (we log our own team): possession *us* → `side='offense'`,
possession *them* → `side='defense'`, special teams → `side='special_teams'`. This
lands live plays in the same substrate the tendency engine already splits on, so ONE
engine and ONE report pipeline serve the logger — no new play tables.

## Backend

- `backend/routers/live_game.py` (prefix `/live`)
  - `POST /session` — create session (sport, teams, date/location, home/away, game
    type, weather/surface, terminology system, custom routes, league format, rosters).
    Enforces `assert_sport_allowed` + `assert_student_consent` (COPPA/FERPA), same as scout.
  - `GET /sessions`, `GET /session/{id}` — list / load (config + plays) for resume + review.
  - `POST /plays` — append plays; on-the-fly jerseys auto-join the session roster.
  - `PATCH /play/{id}`, `DELETE /play/{id}`, `POST /play/{id}/flag` — edit / delete /
    flag a Coaching Point (`is_highlight`, which the report's coach-notes digest reads).
  - `POST /report` — queue a `halftime` (first-half scope) or `full` report.
- `backend/migrations/037_report_params.sql` — nullable `params JSONB` on `tendency_reports`.
- `backend/migrations/038_game_status_live.sql` — adds `'live'` to `games_status_check`.
- `worker_reports._apply_event_filter` — additive, NULL-safe halftime scoping.

## Frontend (`/live`)

- `app/live/page.tsx` — Game Setup + resume list (mobile-first, existing CSS tokens).
- `app/live/[id]/page.tsx` — the logger: period/possession, sport-specific entry
  panels, Quick Log, auto-save per play, Undo, Play Log review (color-coded, tap to
  edit/delete/flag, filters), Halftime / Full Game report buttons.
- `components/live/fields.ts` — sport vocabularies + the three run-gap terminology systems.
- `components/live/Selectors.tsx` — touch SVG selectors: OL gap/hole diagram, flag
  rush lanes, route tree, basketball half-court shot zones.

## Delivered vs. deferred

**Delivered & tested:** all three sports; game setup; the logger with touch SVG
selectors; quick log; play review (edit/delete/flag/filter); halftime + full-game
report generation; delivery via the existing `/reports/[id]` viewer (on-screen, share
link, read-only for staff), saved as a unified game record on the dashboard.

**The bespoke 9-section report** (`backend/services/live_game_report.py`): a dedicated
writer that computes every stat DETERMINISTICALLY in Python from the logged plays
(counts are trustworthy because code counted them), then makes ONE LLM call to write
the coordinator voice. Sections, per the spec:
1. Offensive Summary · 2. Player Tendencies (Our Offense) · 3. Defensive Summary ·
4. Player Tendencies (Opponent) · 5. Special Teams · 6. Top 3 Adjustments ·
7. Coaching Points · 8. Score & Momentum · 9. Season Trend (only when 3+ prior live
games exist for the team+sport; the worker gathers those prior events). Basketball
uses the same nine, shot-zone / possession framed, with a Foul-Trouble Alert banner
(any of our players with 3+ fouls) pinned to the top. Dispatched from `worker_reports`
on `report_type == "live_game"`. Stats layer is unit-tested in `test_live_game_report.py`.

**Deferred (each a separate system, intentionally not stubbed):**
1. Offline PWA sync (service worker + local queue + reconnect flush).
2. Cross-game adaptive-learning suggestions (in-logger banners; the report's Season
   Trend section already uses prior games, but the live suggestion layer is separate).
3. Anonymous collective scouting network (opt-in, cross-team opponent profiles).
4. Native PDF export (report currently shares via the existing link/viewer).

## Discoverability

Reachable at `/live` via a **Live Game** entry in the OSShell sidebar (Analysis
section, "New" badge) — the only edit made to an existing file, one nav item, no
color/style change.
