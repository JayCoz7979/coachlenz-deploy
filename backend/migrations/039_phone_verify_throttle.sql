-- Finding #12: per-user throttle for phone (SMS) verification.
-- /auth/send-phone-code could be looped by any logged-in (even free trial) user
-- to pump Twilio SMS to attacker-chosen numbers — toll fraud. These columns back
-- a 60s cooldown + daily cap per user. Both default safely for existing rows.
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verify_last_sent TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verify_sent_today INTEGER NOT NULL DEFAULT 0;
