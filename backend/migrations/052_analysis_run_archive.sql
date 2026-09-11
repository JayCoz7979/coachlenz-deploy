-- Preserve every AI analysis run. A coach pays for each run, and may want several
-- takes (a cheap Quick Test, then a Deep pass), so a re-run must NEVER silently lose
-- the previous run's plays. Instead of hard-deleting the prior auto-detected plays,
-- the detector archives them here (one row per superseded run, plays stored as JSON),
-- so the active game shows just the current run (reports stay correct) while every
-- prior run stays recoverable until the coach explicitly deletes it.
CREATE TABLE IF NOT EXISTS analysis_run_archives (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id          uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    organization_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    label            text,                        -- e.g. "209 plays · deep · Sep 11"
    play_count       integer NOT NULL DEFAULT 0,
    plays            jsonb NOT NULL DEFAULT '[]'::jsonb,   -- serialized Event rows
    archived_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_run_archive_game ON analysis_run_archives (game_id, archived_at DESC);
