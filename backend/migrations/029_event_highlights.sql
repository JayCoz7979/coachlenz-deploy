-- Film-room highlight marking + coach notes on a tagged play (event).
-- A coach reviewing film can star a play as a highlight and attach a short note;
-- both travel with the event and surface in the play log, cut-ups, and reports.
ALTER TABLE events ADD COLUMN IF NOT EXISTS is_highlight boolean NOT NULL DEFAULT false;
ALTER TABLE events ADD COLUMN IF NOT EXISTS coach_note text;

-- Partial index so "show me the highlights" for a game stays cheap as play counts grow.
CREATE INDEX IF NOT EXISTS ix_events_highlight ON events (game_id) WHERE is_highlight;
