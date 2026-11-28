-- 066: $7 one-time Live Tracker entitlement (Live Game Logger + Halftime Sheet).
-- Product decision (Nov 28): everyone pays $7, including current users. There is NO
-- grandfathering, so every existing org starts with NULL (= not purchased) and the
-- /live write routes refuse until a completed, paid Stripe Checkout sets these.
-- Only ADDS nullable columns; old code ignores them. Idempotent.
-- Numbered 066: 056-061 are claimed by open PRs (#292/#293/#294), 065 is #296.
-- The reverse lives in backend/migrations/down/ (the runner never applies that folder).

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS live_tracker_purchased_at timestamptz;

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS live_tracker_checkout_session_id text;
