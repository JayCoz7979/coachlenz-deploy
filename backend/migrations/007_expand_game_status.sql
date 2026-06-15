-- 007_expand_game_status.sql
-- Expand the games.status CHECK constraint to support the URL-ingest + AI-detection pipeline.
-- Original allowed: pending, processing, ready, error
-- New statuses: queued (URL import created), downloading (yt-dlp fetching),
--               analyzing (AI play detection running)

ALTER TABLE games DROP CONSTRAINT IF EXISTS games_status_check;

ALTER TABLE games ADD CONSTRAINT games_status_check
    CHECK (status IN ('pending','queued','downloading','processing','analyzing','ready','error'));
