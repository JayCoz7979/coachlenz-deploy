"""
Capability-based RBAC for coaching staff (Track 5.1). Pure and framework-free so it
stays unit-testable; auth.py adds the `require_permission` FastAPI dependency.

A user's `role` (on the User model) maps to a set of capabilities. Checks in code
ask "does this role have capability X?" rather than hard-coding role lists, so the
policy lives in one place. Complements scout_roles.py (scout-review authority),
which is unchanged.
"""

# ── Capabilities ─────────────────────────────────────────────────────────────
CAN_RUN_ANALYSIS = "can_run_analysis"
CAN_VIEW_REPORTS = "can_view_reports"
CAN_SHARE_REPORTS = "can_share_reports"
CAN_MANAGE_ROSTER = "can_manage_roster"
CAN_INVITE_STAFF = "can_invite_staff"
CAN_EXPORT_CSV = "can_export_csv"

ALL_CAPABILITIES = frozenset({
    CAN_RUN_ANALYSIS, CAN_VIEW_REPORTS, CAN_SHARE_REPORTS,
    CAN_MANAGE_ROSTER, CAN_INVITE_STAFF, CAN_EXPORT_CSV,
})

# The granular coordinator roles (Track 5.1) plus the legacy generic "coordinator"
# all share the coordinator capability set.
COORDINATOR_ROLES = frozenset({
    "coordinator", "coordinator_offense", "coordinator_defense", "coordinator_special_teams",
})

# ── Role -> capabilities ─────────────────────────────────────────────────────
# owner is the per-org account owner and always has everything. athletic_trainer is
# view-only. Legacy roles (member, reviewer) are retained so existing users keep a
# sensible, non-elevated capability set.
ROLE_PERMISSIONS = {
    "owner": set(ALL_CAPABILITIES),
    "head_coach": {CAN_RUN_ANALYSIS, CAN_VIEW_REPORTS, CAN_SHARE_REPORTS,
                   CAN_MANAGE_ROSTER, CAN_INVITE_STAFF, CAN_EXPORT_CSV},
    "position_coach": {CAN_RUN_ANALYSIS, CAN_VIEW_REPORTS},
    "analyst": {CAN_RUN_ANALYSIS, CAN_VIEW_REPORTS, CAN_SHARE_REPORTS, CAN_EXPORT_CSV},
    "athletic_trainer": {CAN_VIEW_REPORTS},          # view-only
    "reviewer": {CAN_VIEW_REPORTS, CAN_SHARE_REPORTS},  # legacy scout reviewer
    "member": {CAN_VIEW_REPORTS},                    # legacy base
}
for _r in COORDINATOR_ROLES:
    ROLE_PERMISSIONS[_r] = {CAN_RUN_ANALYSIS, CAN_VIEW_REPORTS, CAN_SHARE_REPORTS, CAN_MANAGE_ROSTER}

# Roles a head coach / owner may assign to staff (everything except owner).
STAFF_ASSIGNABLE_ROLES = frozenset(r for r in ROLE_PERMISSIONS if r != "owner")

# Unknown/unset role gets the safest non-empty set: read-only.
_DEFAULT = frozenset({CAN_VIEW_REPORTS})


def role_permissions(role) -> frozenset:
    return frozenset(ROLE_PERMISSIONS.get((role or "").strip().lower(), _DEFAULT))


def has_permission(role, capability: str) -> bool:
    return capability in role_permissions(role)
