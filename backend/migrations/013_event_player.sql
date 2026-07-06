-- Player-level tracking: promote the play's primary actor (ball carrier / passer /
-- target / shooter / tackler jersey) to a first-class, indexable column. Until now
-- it lived only in extra_data.primary_player_jersey, so it could not be queried or
-- aggregated efficiently , the named post-beta gap. Backfill from extra_data so
-- every existing film-detected and manually-entered play is immediately covered.
ALTER TABLE events ADD COLUMN IF NOT EXISTS player VARCHAR;

CREATE INDEX IF NOT EXISTS idx_events_player ON events(player);

UPDATE events
   SET player = extra_data->>'primary_player_jersey'
 WHERE player IS NULL
   AND extra_data ? 'primary_player_jersey'
   AND coalesce(extra_data->>'primary_player_jersey', '') <> '';
