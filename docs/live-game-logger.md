# Live Game Play Logger

Real-time, sideline play-by-play charting for a live game (Football, Flag Football,
Basketball), with a **halftime** and a **full-game** report generated from the logged
plays. New, self-contained module — no existing page, style, route, or table was
modified (only additive files + two additive migrations).

## Access: the $7 Live Tracker (one-time)

The Live Game Logger + Halftime Sheet is a **$7 USD one-time** purchase ("Live
Tracker"). Product decision (Nov 28): **everyone pays $7, including current users**.
There is no grandfathering and no plan, trial, or admin bypass.

- **Landing:** `/live-tracker` (app host). Signed-out coaches go through login or signup
  and come back to `/live-tracker?checkout=1`, which opens checkout.
- **Checkout:** `POST /billing/live-tracker/checkout`: Stripe Checkout, `mode=payment`,
  quantity 1, price id from env **`STRIPE_PRICE_LIVE_TRACKER`** (never an inline
  amount), metadata `kind=live_tracker` + `org_id`. Fails closed with 503 when the price
  or `STRIPE_SECRET_KEY` is unset. 409 if the org already has it.
- **Grant:** only the signed `POST /billing/webhook`, on `checkout.session.completed`
  (or `checkout.session.async_payment_succeeded`) with `payment_status == "paid"`.
  Stored on `organizations.live_tracker_purchased_at` / `live_tracker_checkout_session_id`
  (migration 066). Idempotent twice over: the `processed_stripe_events` marker dedupes
  redeliveries, and the UPDATE only matches an org that has not been granted yet.
  Cancelled, expired, unpaid, or failed sessions grant nothing.
- **Gate (server-side, `backend/services/live_tracker.py`):** every `/live` write route
  (`POST /session`, `POST /plays`, `PATCH|DELETE /play/{id}`, `POST /play/{id}/flag`,
  `POST /report`) returns **402** with `{code: "live_tracker_payment_required",
  message, checkout_path: "/live-tracker"}` for an unpaid org. Read routes
  (`GET /sessions`, `GET /session/{id}`, `GET /access`) stay readable so past games stay
  viewable, and include `access.live_tracker`. Generated reports stay viewable at
  `/reports/{id}`. Student-data consent, the sport lock, and the frontend
  verified-email redirect still apply.
- **Return pages:** success `/live-tracker/success` polls `GET /billing/live-tracker/status`
  until the webhook lands, then opens `/live`. Cancel returns to
  `/live-tracker?checkout=cancelled` with a "you were not charged" note.

Staging env (names only): `STRIPE_PRICE_LIVE_TRACKER` (a TEST-mode one-time $7 price),
test `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (the test webhook endpoint's secret,
subscribed to `checkout.session.completed` and `checkout.session.async_payment_succeeded`).

## Architecture (reuses the existing pipeline)

| Concern            | Reuses                                                              |
|--------------------|--------------------------------------------------------------------|
| Session            | `games` row, `status='live'` (migration 038)                       |
| Setup + rosters    | one `game_meta` event (`side='meta'`), like the proven `scout_meta`|
| Plays              | shared `events` table (`event_type='play'`, `side`, `extra_data`)  |
| Reports            | `Job` → `worker_reports` → `live_game_report` → `/reports/[id]`     |
| Report type        | `live_game` (dispatches to the bespoke 9-section writer)           |
| Report scoping     | `tendency_reports.params.event_filter` (migration 037): whole game / this half / this quarter |

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
  - `POST /report` — queue a report at a `scope`: `full` (whole game) / `this_half` /
    `this_quarter` / `halftime`. `_scope_filter(sport, scope, period)` maps the scope to
    an `event_filter` (min/max quarter or half) + a label; `this_quarter` is the
    "adjustment report" that isolates what the opponent changed after the break.
- `backend/migrations/037_report_params.sql` — nullable `params JSONB` on `tendency_reports`.
- `backend/migrations/038_game_status_live.sql` — adds `'live'` to `games_status_check`.
- `worker_reports._apply_event_filter` — additive, NULL-safe scope filter (min/max
  quarter or half); `build_chart_summary` shapes logged plays into the heat-map fields
  the report viewer already reads, merged into the report summary for `live_game`.

## Frontend (`/live`)

- `app/live/page.tsx` — Game Setup + resume list (mobile-first, existing CSS tokens).
- `app/live/[id]/page.tsx` — the logger: period/possession, sport-specific entry
  panels, Quick Log, auto-save per play, Undo, Play Log review (color-coded, tap to
  edit/delete/flag, filters), Halftime / Full Game report buttons.
- `components/live/fields.ts` — sport vocabularies + the three run-gap terminology systems.
- `components/live/Selectors.tsx` — touch SVG selectors: OL gap/hole diagram, flag
  rush lanes, route tree, pass target-area grid, and a real HIGH-SCHOOL (NFHS)
  half-court (tap the spot → drops a marker, auto-resolves the 10-zone value + coords).
- `components/report/LiveShotChart.tsx` — the report's true shot-location court (us +
  opponent, made/miss, fouled-attempt rings, Us/Opponent/Both toggle). The football
  field heat maps and basketball zone chart reuse the existing `report/` components
  (`FieldHeatMap`, `RunPassMatrix`, `RunDirectionArrows`, `BasketballShotChart`).

## Reports, heat maps & examples

The report renders in the existing `/reports/[id]` viewer. It carries:
- **Nine coordinator-voice sections** (basketball adds a Foul-Trouble Alert banner),
  scoped to the chosen segment (whole game / this half / this quarter).
- **Heat maps**, from `build_chart_summary` merged into `report.summary`:
  - Football / flag: **run-gap** (football) or **rush-lane** (flag) tiles + a
    **pass-target field grid** (`FieldHeatMap`), toggle Volume / Success% / Avg-Yds.
    Success = gain-of-4+ for both run and pass, so the scale is apples-to-apples.
  - Basketball: a **shot-zone chart** (`BasketballShotChart`) + a **true shot-location
    court** (`LiveShotChart`) showing both teams' shots, made/miss, and fouled attempts.
- **Season Trend Comparison** (Section 9): activates once the team has 3+ prior `live`
  games; the worker pools their events via `compute_season_baseline` and the section
  compares tonight's rates to that baseline. Suppressed on single-quarter scopes.

**Worked examples** in [`docs/examples/`](examples/) — one full-game report per sport,
illustrative (real-pipeline stats + heat maps; hand-authored prose to show the format).
Open in a browser:
- [`live-game-football-report.example.html`](examples/live-game-football-report.example.html)
  — run-gap + pass field heat maps; A-gap-keyed / B-gap-counter tell.
- [`live-game-flag-report.example.html`](examples/live-game-flag-report.example.html)
  — rush-lane + pass field heat maps (flag terminology).
- [`live-game-basketball-report.example.html`](examples/live-game-basketball-report.example.html)
  — Foul-Trouble Alert, shot-zone chart, true shot-location court (us + opponent +
  fouled-attempt rings), and an **active Season Trend** (game 4 vs a 3-game baseline).

## Delivered vs. deferred

**Delivered & tested:** all three sports; game setup; the logger with touch SVG
selectors (incl. a real HS half-court + pass target-area grid); quick log; play review
(edit/delete/flag/filter); scoped reports (whole game / this half / this-quarter
adjustment view); the 9-section coordinator report; heat maps (run/rush + pass field
maps, basketball shot chart + true shot-location court with both teams and fouled
attempts); the Season Trend Comparison at 3+ games; delivery via the existing
`/reports/[id]` viewer (on-screen, share link, read-only for staff), saved as a
unified game record on the dashboard.

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

## Free printable Halftime Sheet PDF (double opt-in lead form)

The `/live-tracker` page also offers a free printable Halftime Sheet (2 pages: one for Football and Flag Football, one for Basketball) in exchange for a name and an email address. Phone is optional and is never texted. There is no SMS anywhere.

Flow (double opt-in):

1. `POST /leads/halftime-sheet` `{name, email, phone?, consent, company}`. The server checks the format, blocks common disposable domains, and checks MX/domain (falling back to A/AAAA records; a DNS outage fails open, because nothing is delivered until the inbox owner clicks). It stores the lead in `halftime_pdf_leads` with `status='pending'` and `source='halftime_pdf'`, then emails a single-use confirmation link that expires in 24 hours. `company` is a honeypot: if it is filled in, the server returns the normal success answer and stores nothing.
2. The coach opens `/live-tracker/halftime-sheet/confirm?token=…` and clicks **Confirm my email**. That sends `POST /leads/halftime-sheet/confirm {token}`, which sets `status='confirmed'`, `confirmed_at`, and `confirmed_ip`, and only **then** emails the PDF as an attachment. No endpoint returns the PDF. Confirming is a click, not an automatic page load, so a mail scanner that prefetches links cannot use up the token.
3. Expired, used, or replaced links show a clear message and a resend option: `POST /leads/halftime-sheet/resend {token}` or `{email}`. Each new link replaces the old one.

Security:
- Tokens are stored only as `HMAC-SHA256(SECRET_KEY, token)`.
- Single use is enforced by an atomic `UPDATE … WHERE token_used_at IS NULL AND token_expires_at > now`.
- Rate limits per IP: submit 5/min and 30/hr, resend 3/min and 20/hr, confirm 20/min. Each address also has a 60-second resend cooldown, which starts only after a send succeeds.
- Submit and resend give the same answer for every address, so they can't be used to look up who is on the list.

Outbound safety (staging): lead emails are sent through the existing Resend provider **only** to `LEAD_EMAIL_ALLOWLIST` addresses (comma-separated emails or `@domain` entries) unless `LEAD_EMAIL_LIVE_SEND=true`. That flag defaults to off, so staging cannot email a real coach. Set `LEAD_CONFIRM_BASE_URL` to the staging frontend so confirm links do not point at production.

Code: `backend/routers/halftime_leads.py`, `backend/services/halftime_leads.py`, `backend/services/halftime_pdf.py`, migration `067_halftime_pdf_leads.sql`. UI: `frontend/components/live/HalftimePdfForm.tsx`, `frontend/app/live-tracker/halftime-sheet/confirm/page.tsx`. Tests: `backend/tests/test_halftime_leads.py` (unit), `backend/tests/test_halftime_leads_pg.py` (real Postgres, skipped unless `MIGRATIONS_TEST_DATABASE_URL` is set), `frontend/tests/halftime-lead.test.ts`.
