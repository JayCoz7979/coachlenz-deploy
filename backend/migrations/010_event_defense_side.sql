-- 010_event_defense_side.sql
-- Two-sided scouting: tag whether a play is the scouted team's OFFENSE or DEFENSE,
-- and capture defensive attributes (front, coverage, blitz).

ALTER TABLE events ADD COLUMN IF NOT EXISTS side TEXT NOT NULL DEFAULT 'offense';
ALTER TABLE events ADD COLUMN IF NOT EXISTS defensive_front TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS coverage TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS blitz TEXT;

-- Backfill existing rows as offense (they were all offensive tags).
UPDATE events SET side = 'offense' WHERE side IS NULL;
