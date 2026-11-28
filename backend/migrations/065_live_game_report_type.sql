-- 065: allow report_type 'live_game' on tendency_reports.
-- Root cause of "Live Game Logger reports fail": 001_initial_schema.sql limited report_type to
-- opponent, self_scout, custom (tendency_reports_report_type_check). POST /live/report inserts
-- 'live_game', so every logger report INSERT failed (HTTP 500).
-- Only WIDENS the allowed set; old code keeps working, so a code rollback needs no schema rollback.
-- Numbered 065 on purpose: #294 carries 056-061 and may add more; 062-064 stay free. The runner
-- applies unapplied files in sorted order, so the gap is harmless. Idempotent.
-- The reverse lives in backend/migrations/down/ (the runner never applies that subfolder).

ALTER TABLE tendency_reports
    DROP CONSTRAINT IF EXISTS tendency_reports_report_type_check;

ALTER TABLE tendency_reports
    ADD CONSTRAINT tendency_reports_report_type_check
    CHECK (report_type IN ('opponent', 'self_scout', 'custom', 'live_game'));
