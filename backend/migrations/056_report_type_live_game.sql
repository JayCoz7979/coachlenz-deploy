-- The Live Game logger writes report_type = 'live_game' (routers/live_game.py),
-- and POST /reports accepts the same value. The original check (migration 001)
-- only allowed opponent, self_scout, and custom, so a live_game insert failed
-- the constraint and the API returned 500.
--
-- Reverse (only when no row has report_type = 'live_game'):
--   ALTER TABLE tendency_reports DROP CONSTRAINT IF EXISTS tendency_reports_report_type_check;
--   ALTER TABLE tendency_reports ADD CONSTRAINT tendency_reports_report_type_check
--       CHECK (report_type IN ('opponent', 'self_scout', 'custom'));

ALTER TABLE tendency_reports DROP CONSTRAINT IF EXISTS tendency_reports_report_type_check;
ALTER TABLE tendency_reports ADD CONSTRAINT tendency_reports_report_type_check
    CHECK (report_type IN ('opponent', 'self_scout', 'custom', 'live_game'));
