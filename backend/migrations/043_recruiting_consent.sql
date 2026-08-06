-- Finding #17: per-player directory-disclosure consent for the public Recruiting
-- Board. Enabling a public recruiting link publishes a minor's name + film + stats
-- to third parties, which is a separate authorization from the student_data
-- collection attestation. Record who consented, when, and to which version.
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS recruiting_consent_at timestamptz;
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS recruiting_consent_by uuid;
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS recruiting_consent_version text;
