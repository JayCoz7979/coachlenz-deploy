-- Live Game Play Logger reports are stored with report_type='live_game'
-- (backend/routers/live_game.py), and both the report worker and the report
-- viewer dispatch on that exact value. But the original tendency_reports CHECK
-- constraint (001_initial_schema.sql) only permitted 'opponent','self_scout',
-- 'custom'. So EVERY live-game report INSERT failed at commit with a
-- CheckViolationError: the free POST /live/report returned a 500 and the sideline
-- UI showed the generic "Could not generate the report." for both the whole-game
-- and the this-quarter reports. Add 'live_game' to the allowed set so the free
-- Live Game Logger can actually produce its halftime / full-game report.
--
-- Additive, idempotent, and a no-op for every existing scout/film report (all of
-- which already use an allowed value): drop-if-exists, then re-create with the
-- full value set.
ALTER TABLE tendency_reports DROP CONSTRAINT IF EXISTS tendency_reports_report_type_check;
ALTER TABLE tendency_reports ADD CONSTRAINT tendency_reports_report_type_check
    CHECK (report_type IN ('opponent', 'self_scout', 'custom', 'live_game'));
