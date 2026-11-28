-- 066: the $7 one-time Live Tracker unlock (Live Game Logger + Halftime Sheet).
-- The grant lives on the org. NULL = not purchased (the /live gate refuses). The
-- webhook sets it once, only after Stripe reports the Checkout Session as paid, and
-- only WHERE it is still NULL, so a redelivered or second event never re-grants or
-- moves the timestamp. The session id is kept as the receipt for support/refunds.
-- Numbered 066 on purpose: #294 carries 056-061 (and may add more), 062-064 stay
-- free, and 065 is the live_game report-type fix from #296. Idempotent; only ADDS
-- nullable columns, so old code keeps working and a code rollback needs no schema
-- rollback. Existing orgs are NOT backfilled: everyone pays $7, including current
-- users (product decision, Nov 28 2026). No grandfathering.
-- The reverse lives in backend/migrations/down/ (the runner never applies that folder).

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS live_tracker_purchased_at timestamptz,
    ADD COLUMN IF NOT EXISTS live_tracker_checkout_session_id text;
