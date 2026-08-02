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
| Reports            | `Job` → `worker_reports` → `report_writer` → `/reports/[id]`        |
| Report type        | `self_scout` (an "us"-oriented report of our own tendencies)       |
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
report generation wired to the live report pipeline; delivery via the existing
`/reports/[id]` viewer (on-screen, share link, read-only for staff), saved as a
unified game record on the dashboard.

**Deferred (each a separate system, intentionally not stubbed):**
1. Offline PWA sync (service worker + local queue + reconnect flush).
2. Cross-game adaptive-learning suggestions (needs 3+ games; suggestion banners).
3. Anonymous collective scouting network (opt-in, cross-team opponent profiles).
4. Native PDF export (report currently shares via the existing link/viewer).
5. A **bespoke live-game report writer** matching the exact 9-section spec format
   (opponent player tendencies, special-teams, momentum). Today the report uses the
   existing `self_scout` writer — a real, first-half-scoped breakdown of our tendencies.

## Discoverability

Reachable at `/live` via a **Live Game** entry in the OSShell sidebar (Analysis
section, "New" badge) — the only edit made to an existing file, one nav item, no
color/style change.
