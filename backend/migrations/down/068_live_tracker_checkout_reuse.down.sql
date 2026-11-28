-- Reverse of 068_live_tracker_checkout_reuse.sql. Never applied by the migration runner.
-- Export live_tracker_extra_payments first: it is the list of payments to refund.
DROP TABLE IF EXISTS live_tracker_extra_payments;
ALTER TABLE organizations
    DROP COLUMN IF EXISTS live_tracker_open_session_expires_at,
    DROP COLUMN IF EXISTS live_tracker_open_session_id;
DELETE FROM schema_migrations WHERE filename = '068_live_tracker_checkout_reuse.sql';
