-- Team attribution: capture each side's on-field appearance so the vision agent can
-- tell which team is which (e.g. "scout the WHITE jerseys"). Without this the
-- offense/defense labels aren't reliably tied to a specific team.
ALTER TABLE games ADD COLUMN IF NOT EXISTS scout_jersey VARCHAR;
ALTER TABLE games ADD COLUMN IF NOT EXISTS opponent_jersey VARCHAR;
