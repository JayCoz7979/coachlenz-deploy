-- Email verification (chargeback protection, step 1 of onboarding). A 6-digit
-- code is emailed via Resend; only its SHA-256 hash + expiry are stored here.
-- Phone verification uses Twilio Verify, which stores its own codes (no columns).
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_code_hash text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_expires timestamptz;
