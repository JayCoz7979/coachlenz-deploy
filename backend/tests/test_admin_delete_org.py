"""
Admin org deletion: 404 for a missing org, 400 self-lockout guard, and a clean
delete with a summary. Driven with a DB stub (require_admin is bypassed by calling
the handler directly with an admin-shaped user).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers.admin import delete_org


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.deleted = []

    async def execute(self, *_a, **_k):
        return self._results.pop(0)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        return None


def _admin(org="admin-org"):
    return SimpleNamespace(id="admin-user", organization_id=org)


def _org(oid="target-org"):
    return SimpleNamespace(id=oid, name="Phase0 Smoke Org", slug="phase0-smoke-org-ab12")


def test_delete_org_not_found_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_org("missing", user=_admin(), db=_FakeDB([_Result(None)])))
    assert exc.value.status_code == 404


def test_cannot_delete_own_org_400():
    org = _org("admin-org")  # same id as the admin's organization
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_org("admin-org", user=_admin("admin-org"), db=_FakeDB([_Result(org)])))
    assert exc.value.status_code == 400


def test_delete_org_success():
    org = _org("target-org")
    db = _FakeDB([_Result(org), _Result(3)])  # org lookup, then user count
    out = asyncio.run(delete_org("target-org", user=_admin("admin-org"), db=db))
    assert out["ok"] is True
    assert out["deleted"]["name"] == "Phase0 Smoke Org"
    assert out["users_removed"] == 3
    assert db.deleted and db.deleted[0] is org
