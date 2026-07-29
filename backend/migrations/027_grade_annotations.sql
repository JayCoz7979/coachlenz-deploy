-- Player Grades Board: coach notes on a player's grade for a specific play.
CREATE TABLE IF NOT EXISTS grade_annotations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    game_id uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    event_id uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    jersey text,
    note text NOT NULL,
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_grade_annotations_game ON grade_annotations (game_id);
CREATE INDEX IF NOT EXISTS ix_grade_annotations_event ON grade_annotations (event_id);
