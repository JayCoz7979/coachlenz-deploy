-- Recruiting Board: opt-in, shareable player showcase for college scouts.
-- Per-player opt-in + share token (default 30-day, 90-day max) on the roster.
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS recruiting_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS recruiting_token text;
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS recruiting_expires_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS ix_roster_recruiting_token
    ON roster_players (recruiting_token) WHERE recruiting_token IS NOT NULL;

-- A clip becomes a player's recruiting highlight by pointing at a roster player.
ALTER TABLE clips ADD COLUMN IF NOT EXISTS recruiting_player_id uuid
    REFERENCES roster_players(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_clips_recruiting_player ON clips (recruiting_player_id);
