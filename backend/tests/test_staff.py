"""
Track 5.1 - staff invite / role / revoke flow. Driven with a DB stub + a
monkeypatched email send (no network), asserting the business rules.
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.routers.staff as staff


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.added = []

    async def execute(self, *_a, **_k):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


def _inviter(role="head_coach"):
    return SimpleNamespace(id="inv1", organization_id="o1", name="Coach HC", role=role)


def _org():
    return SimpleNamespace(id="o1", name="Test HS")


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    async def _noop(*_a, **_k):
        return None
    monkeypatch.setattr(staff, "send_staff_invite_email", _noop)


# ── invite ───────────────────────────────────────────────────────────────────
def test_invite_rejects_unassignable_role():
    body = staff.InviteIn(email="x@y.com", name="X", role="wizard")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(staff.invite_staff(body, inviter=_inviter(), org=_org(), db=_FakeDB([])))
    assert exc.value.status_code == 422


def test_invite_rejects_existing_email():
    body = staff.InviteIn(email="dupe@y.com", name="Dupe", role="analyst")
    db = _FakeDB([_Result(SimpleNamespace(id="u2"))])  # email already exists
    with pytest.raises(HTTPException) as exc:
        asyncio.run(staff.invite_staff(body, inviter=_inviter(), org=_org(), db=db))
    assert exc.value.status_code == 409


def test_invite_creates_staff_with_role_and_token():
    body = staff.InviteIn(email="new@y.com", name="New Coach", role="analyst")
    db = _FakeDB([_Result(None)])  # no existing email
    out = asyncio.run(staff.invite_staff(body, inviter=_inviter(), org=_org(), db=db))
    assert out["invited"] is True and out["role"] == "analyst"
    created = db.added[0]
    assert created.organization_id == "o1"
    assert created.reset_token_hash and created.reset_token_expires > datetime.utcnow()
    assert created.is_active is True


# ── role change ──────────────────────────────────────────────────────────────
def test_set_role_cannot_change_owner():
    target = SimpleNamespace(id="t1", organization_id="o1", role="owner", name="Owner")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(staff.set_staff_role("t1", staff.RoleIn(role="analyst"),
                                         inviter=_inviter(), db=_FakeDB([_Result(target)])))
    assert exc.value.status_code == 403


def test_set_role_updates_target():
    target = SimpleNamespace(id="t1", organization_id="o1", role="analyst", name="A",
                             email="a@y.com", is_active=True)
    out = asyncio.run(staff.set_staff_role("t1", staff.RoleIn(role="position_coach"),
                                           inviter=_inviter(), db=_FakeDB([_Result(target)])))
    assert target.role == "position_coach" and out["role"] == "position_coach"


# ── revoke ───────────────────────────────────────────────────────────────────
def test_revoke_blocks_owner():
    target = SimpleNamespace(id="t1", organization_id="o1", role="owner")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(staff.revoke_staff("t1", inviter=_inviter(), db=_FakeDB([_Result(target)])))
    assert exc.value.status_code == 403


def test_revoke_blocks_self():
    target = SimpleNamespace(id="inv1", organization_id="o1", role="head_coach")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(staff.revoke_staff("inv1", inviter=_inviter(), db=_FakeDB([_Result(target)])))
    assert exc.value.status_code == 400


def test_revoke_deactivates_and_bumps_token_version():
    target = SimpleNamespace(id="t1", organization_id="o1", role="analyst",
                             is_active=True, token_version=0)
    out = asyncio.run(staff.revoke_staff("t1", inviter=_inviter(), db=_FakeDB([_Result(target)])))
    assert out["revoked"] is True
    assert target.is_active is False          # access token now filtered out
    assert target.token_version == 1          # refresh tokens revoked


def test_reactivate_restores_access():
    target = SimpleNamespace(id="t1", organization_id="o1", role="analyst", is_active=False)
    out = asyncio.run(staff.reactivate_staff("t1", inviter=_inviter(), db=_FakeDB([_Result(target)])))
    assert out["is_active"] is True and target.is_active is True
