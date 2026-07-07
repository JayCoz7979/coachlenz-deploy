-- Bootstrap the platform superadmin.
-- "Superadmin" in CoachLenz == a user with role 'owner': the /admin platform
-- area and owner-only controls are gated by require_role("owner") (see
-- backend/routers/admin.py). Grant the owner role to the founder's account so
-- aiwithjaycoz@gmail.com can administer the back office.
--
-- Safety: this ONLY elevates an EXISTING account's role. It never creates a
-- user or sets a password (accounts are created via signup). It is a no-op if
-- the account does not exist yet, in which case aiwithjaycoz@gmail.com must be
-- registered at app.coachlenz.com/login first, then re-granted. Case-insensitive
-- match; idempotent and one-shot (tracked in schema_migrations).
UPDATE users
SET role = 'owner', updated_at = now()
WHERE lower(email) = 'aiwithjaycoz@gmail.com'
  AND role <> 'owner';
