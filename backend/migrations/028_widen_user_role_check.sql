-- The original users_role_check (migration 001) only allowed
-- owner/admin/coach/member, which rejected every coaching-staff role the RBAC and
-- staff-invite features assign (analyst, head_coach, coordinator_*, position_coach,
-- athletic_trainer, reviewer). Widen it. Keep in sync with
-- models.user.ALLOWED_USER_ROLES (guarded by test_role_constraint).
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN (
    'admin', 'analyst', 'athletic_trainer', 'coach', 'coordinator',
    'coordinator_defense', 'coordinator_offense', 'coordinator_special_teams',
    'head_coach', 'member', 'owner', 'position_coach', 'reviewer'
));
