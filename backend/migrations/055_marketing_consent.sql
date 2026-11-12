-- Marketing permission. Capture an explicit opt-in at signup so coaches can be emailed
-- product updates, and give every user a stable unsubscribe token so one-click opt-out
-- (CAN-SPAM) works for anyone, opted-in or not. Existing rows default to NOT opted in
-- (false), which matches today's behavior: nobody has consented yet.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS marketing_opt_in boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS marketing_opt_in_at timestamptz,
    ADD COLUMN IF NOT EXISTS unsubscribe_token text;

-- Backfill a token for every existing user; new users get one at creation (ORM default).
UPDATE users
    SET unsubscribe_token = replace(gen_random_uuid()::text, '-', '')
    WHERE unsubscribe_token IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS users_unsubscribe_token_key ON users (unsubscribe_token);
