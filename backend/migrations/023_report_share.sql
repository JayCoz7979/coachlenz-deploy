-- Read-only public share links for scouting reports. Null until a coach enables
-- sharing; expiry-gated (7-day default, 30-day max) and revocable.
ALTER TABLE tendency_reports ADD COLUMN IF NOT EXISTS share_token text;
ALTER TABLE tendency_reports ADD COLUMN IF NOT EXISTS share_expires_at timestamptz;
ALTER TABLE tendency_reports ADD COLUMN IF NOT EXISTS share_view_count integer NOT NULL DEFAULT 0;
-- Unique per non-null token (partial index so many un-shared reports keep NULL).
CREATE UNIQUE INDEX IF NOT EXISTS ix_tendency_reports_share_token
    ON tendency_reports (share_token) WHERE share_token IS NOT NULL;
