-- Password reset support. A forgot-password request stores a SHA-256 hash of a
-- single-use, short-lived reset token on the user row (never the raw token), plus
-- its expiry. reset-password looks the user up by the token hash, verifies it has
-- not expired, sets the new password, and clears both columns (single use).
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_hash text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires timestamptz;
