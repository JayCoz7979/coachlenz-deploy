-- Team rosters: named players keyed to a jersey number, so EAGLE-EYE jersey reads
-- resolve to a player. Season + sport come from the team.
CREATE TABLE IF NOT EXISTS roster_players (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    jersey_number text NOT NULL,
    first_name text NOT NULL,
    last_name text,
    position text,
    grade_year text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_roster_team_jersey UNIQUE (team_id, jersey_number)
);
CREATE INDEX IF NOT EXISTS ix_roster_players_org ON roster_players (organization_id);
CREATE INDEX IF NOT EXISTS ix_roster_players_team ON roster_players (team_id);
