-- 066 down: drop the Live Tracker grant columns. Run by hand only.
-- WARNING: this forgets every recorded $7 purchase. Export the rows first:
--   SELECT id, live_tracker_purchased_at, live_tracker_checkout_session_id
--   FROM organizations WHERE live_tracker_purchased_at IS NOT NULL;
BEGIN;

ALTER TABLE organizations
    DROP COLUMN IF EXISTS live_tracker_checkout_session_id,
    DROP COLUMN IF EXISTS live_tracker_purchased_at;

DELETE FROM schema_migrations WHERE filename = '066_live_tracker_entitlement.sql';

COMMIT;
