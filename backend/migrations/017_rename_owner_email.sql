-- Owner requested: make the personal Gmail the superadmin login.
-- Rename the existing owner account info@cosbyaisolutions.com -> aiwithjaycoz@gmail.com
-- (the account id / password are unchanged; only the login email changes) and
-- (re)assert role='owner' so it is the platform superadmin (gates /admin via
-- require_role("owner")).
--
-- Safety: guarded by NOT EXISTS so it can NEVER raise a unique-email violation —
-- if aiwithjaycoz@gmail.com is already a separate account, this is a no-op (and
-- the rename must be handled manually). Case-insensitive; one-shot (tracked).
UPDATE users
SET email = 'aiwithjaycoz@gmail.com', role = 'owner', updated_at = now()
WHERE lower(email) = 'info@cosbyaisolutions.com'
  AND NOT EXISTS (
    SELECT 1 FROM users u2 WHERE lower(u2.email) = 'aiwithjaycoz@gmail.com'
  );
