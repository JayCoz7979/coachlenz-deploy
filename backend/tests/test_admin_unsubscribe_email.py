"""Admin unsubscribe-by-email. No inbox reader and no Resend call."""
import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.models.marketing_consent import EmailSuppression, MarketingConsentEvent
from backend.routers.admin import require_unsubscribe_admin, unsubscribe_lead_by_email
from backend.routers.admin import EmailUnsubscribe


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self, batches):
        self.batches = list(batches)
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        rows = self.batches.pop(0) if self.batches else []
        return _Rows(rows)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _call(email, batches):
    db = _DB(batches)
    out = asyncio.run(unsubscribe_lead_by_email(EmailUnsubscribe(email=email), SimpleNamespace(), db))
    return out, db


@pytest.mark.unit
def test_non_admin_unsubscribe_is_403(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")
    user = SimpleNamespace(email="coach@school.edu")
    org = SimpleNamespace(admin_level=None)
    with pytest.raises(HTTPException) as exc:
        require_unsubscribe_admin(user, org)
    assert exc.value.status_code == 403


@pytest.mark.unit
def test_unknown_email_is_a_noop(caplog):
    caplog.set_level(logging.INFO)
    out, db = _call("missing@school.edu", [[], []])
    assert out == {"ok": True, "updated": False}
    assert db.added == [] and db.commits == 0
    assert "missing@school.edu" not in caplog.text


@pytest.mark.unit
def test_repeated_unsubscribe_by_email_is_safe(caplog):
    caplog.set_level(logging.INFO)
    lead = SimpleNamespace(id="lead-1", email="Coach@School.edu", unsubscribed_at=None, role="head_coach")
    account = SimpleNamespace(email="Coach@School.edu", marketing_opt_in=True)
    db = _DB([[lead], [account]])
    first = asyncio.run(unsubscribe_lead_by_email(
        EmailUnsubscribe(email="  Coach@School.edu "), SimpleNamespace(), db))
    assert first == {"ok": True, "updated": True}
    assert lead.unsubscribed_at is not None
    assert account.marketing_opt_in is False
    assert any(isinstance(obj, EmailSuppression) for obj in db.added)
    assert any(isinstance(obj, MarketingConsentEvent) and obj.unsubscribe_method == "admin_email" for obj in db.added)
    assert "Coach@School.edu" not in caplog.text
    added_before = len(db.added)
    db.batches = [[lead], [account]]
    second = asyncio.run(unsubscribe_lead_by_email(
        EmailUnsubscribe(email="coach@school.edu"), SimpleNamespace(), db))
    assert second == {"ok": True, "updated": False}
    assert len(db.added) == added_before
    assert db.commits == 2
