"""
Track 5.1 - capability-based RBAC matrix + require_permission gate.
Pure matrix logic plus the dependency's allow/deny behavior (no DB needed).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.permissions import (
    role_permissions, has_permission, ROLE_PERMISSIONS, ALL_CAPABILITIES,
    COORDINATOR_ROLES, STAFF_ASSIGNABLE_ROLES,
    CAN_RUN_ANALYSIS, CAN_VIEW_REPORTS, CAN_SHARE_REPORTS, CAN_MANAGE_ROSTER,
    CAN_INVITE_STAFF, CAN_EXPORT_CSV,
)
from backend.services.auth import require_permission


def test_rbac_coaching_roles_defined():
    for role in ("head_coach", "coordinator_offense", "coordinator_defense",
                 "coordinator_special_teams", "position_coach", "analyst",
                 "athletic_trainer", "owner"):
        assert role in ROLE_PERMISSIONS, role
    # Owner can't be assigned to staff; the rest can.
    assert "owner" not in STAFF_ASSIGNABLE_ROLES
    assert "head_coach" in STAFF_ASSIGNABLE_ROLES


def test_owner_has_all_capabilities():
    assert role_permissions("owner") == ALL_CAPABILITIES


def test_head_coach_can_invite_and_manage():
    assert has_permission("head_coach", CAN_INVITE_STAFF)
    assert has_permission("head_coach", CAN_MANAGE_ROSTER)
    assert has_permission("head_coach", CAN_EXPORT_CSV)


def test_position_coach_cannot_invite_staff():
    assert not has_permission("position_coach", CAN_INVITE_STAFF)
    assert not has_permission("position_coach", CAN_MANAGE_ROSTER)
    assert has_permission("position_coach", CAN_RUN_ANALYSIS)   # can still analyze
    assert has_permission("position_coach", CAN_VIEW_REPORTS)


def test_athletic_trainer_view_only():
    assert role_permissions("athletic_trainer") == frozenset({CAN_VIEW_REPORTS})


def test_analyst_can_export_but_not_manage_or_invite():
    assert has_permission("analyst", CAN_EXPORT_CSV)
    assert has_permission("analyst", CAN_SHARE_REPORTS)
    assert not has_permission("analyst", CAN_MANAGE_ROSTER)
    assert not has_permission("analyst", CAN_INVITE_STAFF)


def test_all_coordinator_variants_manage_roster_but_not_invite():
    for role in COORDINATOR_ROLES:
        assert has_permission(role, CAN_MANAGE_ROSTER), role
        assert not has_permission(role, CAN_INVITE_STAFF), role


def test_unknown_or_missing_role_is_view_only():
    assert role_permissions("not-a-role") == frozenset({CAN_VIEW_REPORTS})
    assert role_permissions(None) == frozenset({CAN_VIEW_REPORTS})
    assert not has_permission(None, CAN_RUN_ANALYSIS)


# ── the dependency ───────────────────────────────────────────────────────────
def _run_checker(capability, role):
    checker = require_permission(capability)
    return asyncio.run(checker(user=SimpleNamespace(role=role)))


def test_require_permission_allows_capable_role():
    user = _run_checker(CAN_INVITE_STAFF, "head_coach")
    assert user.role == "head_coach"


def test_require_permission_blocks_incapable_role():
    with pytest.raises(HTTPException) as exc:
        _run_checker(CAN_INVITE_STAFF, "position_coach")
    assert exc.value.status_code == 403
