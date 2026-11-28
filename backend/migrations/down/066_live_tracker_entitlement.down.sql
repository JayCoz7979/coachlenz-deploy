-- 066 down: drop the Live Tracker entitlement columns. Run by hand only.
-- WARNING: this forgets which orgs paid the $7. Export the rows first:
--   SELECT id, live_tracker_purchased_at, live_tracker_checkout_session_id
--   FROM organizations WHERE live_tracker_purchased_at IS NOT NULL;
ALTER TABLE organizations DROP COLUMN IF EXISTS live_tracker_checkout_session_id;
ALTER TABLE organizations DROP COLUMN IF EXISTS live_tracker_purchased_at;
