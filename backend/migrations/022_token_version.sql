-- Refresh-token revocation. A monotonically increasing counter per user; refresh
-- tokens embed its value at issue time and /auth/refresh rejects any token whose
-- version is stale. Incremented on logout, password change, and password reset to
-- invalidate ALL of a user's refresh tokens (every device) at once.
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version integer NOT NULL DEFAULT 0;
