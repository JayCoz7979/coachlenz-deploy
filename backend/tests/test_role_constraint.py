"""
Guard for the production bug Phase 0 found: users.role has a DB CHECK constraint
(migration 001) that rejected coaching roles like 'analyst'. The fix widens it
(migration 028) and declares it on the model. These tests keep the model, the
migration, and the RBAC role set from drifting apart again.
"""
import pathlib
import re

from backend.models.user import ALLOWED_USER_ROLES
from backend.services.permissions import ROLE_PERMISSIONS, STAFF_ASSIGNABLE_ROLES
from backend.services.scout_roles import SCOUT_ASSIGNABLE_ROLES


def test_every_assignable_role_is_db_allowed():
    # Any role the app can put on a user MUST be permitted by the DB constraint.
    assert set(ROLE_PERMISSIONS) <= ALLOWED_USER_ROLES
    assert set(STAFF_ASSIGNABLE_ROLES) <= ALLOWED_USER_ROLES
    assert set(SCOUT_ASSIGNABLE_ROLES) <= ALLOWED_USER_ROLES


def test_migration_role_list_matches_model():
    sql = (pathlib.Path(__file__).parents[1] / "migrations" / "028_widen_user_role_check.sql").read_text()
    m = re.search(r"CHECK \(role IN \((.*?)\)\)", sql, re.S)
    assert m, "could not find the CHECK clause in migration 028"
    migration_roles = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert migration_roles == set(ALLOWED_USER_ROLES), (
        f"migration 028 and models.user.ALLOWED_USER_ROLES drift: "
        f"{migration_roles ^ set(ALLOWED_USER_ROLES)}"
    )
