"""Stage 2 round 2, LOW 2: halftime_pdf_leads is in the privacy export and deletion flows,
matched by the requester's email (case-insensitive). No DB: the session is faked."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import privacy as router
from backend.services import privacy_requests as svc


class _Result:
    def __init__(self, v):
        self.v = v

    def scalar_one_or_none(self):
        return self.v

    def scalars(self):
        items = self.v if isinstance(self.v, list) else ([] if self.v is None else [self.v])
        return SimpleNamespace(all=lambda: items)


class _DB:
    def __init__(self, results):
        self._r = list(results)
        self.queries = []
        self.deleted = []
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt, *_a, **_k):
        self.queries.append(stmt)
        return self._r.pop(0)

    async def delete(self, o):
        self.deleted.append(o)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _run(c):
    return asyncio.run(c)


def _lead(email="qa.coach@example.com"):
    ts = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111", name="Test Coach", email=email,
        phone=None, source="halftime_pdf", status="confirmed",
        consent_text="I agree that CoachLenz may email me...", consented_at=ts,
        submit_ip="203.0.113.7", token_hash="deadbeef" * 8, token_expires_at=ts,
        token_used_at=ts, confirmation_sent_at=ts, confirmation_send_count=1,
        confirmed_at=ts, confirmed_ip="203.0.113.8", pdf_sent_at=ts, unsubscribed_at=None,
        created_at=ts, updated_at=ts)


def _pr(**kw):
    base = dict(id="22222222-2222-2222-2222-222222222222", request_type="deletion",
                status="verified", requester_email="QA.Coach@Example.com",
                requester_name="Test Coach", relationship="other", student_name="n/a",
                organization_id=None, resolution_note=None, created_at=None,
                certificate_id=None, completed_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


_ADMIN = SimpleNamespace(email="admin@example.com")


# ── service ────────────────────────────────────────────────────────────────────
def test_find_leads_matches_lowercased_email():
    db = _DB([_Result([_lead()])])
    rows = _run(svc.find_leads_by_email(db, "  QA.Coach@Example.COM "))
    assert len(rows) == 1
    sql = str(db.queries[0].compile(compile_kwargs={"literal_binds": True}))
    assert "lower(halftime_pdf_leads.email) = 'qa.coach@example.com'" in sql


def test_find_leads_blank_email_queries_nothing():
    db = _DB([])
    assert _run(svc.find_leads_by_email(db, "  ")) == []
    assert db.queries == []


def test_export_includes_personal_fields_and_never_the_token_hash():
    db = _DB([_Result([_lead()])])
    data = _run(svc.export_personal_data_by_email(db, "qa.coach@example.com"))
    assert data["email"] == "qa.coach@example.com"
    (rec,) = data["halftime_pdf_leads"]
    for f in ("name", "email", "phone", "source", "status", "consent_text", "submit_ip",
              "confirmed_ip", "confirmed_at", "pdf_sent_at", "created_at"):
        assert f in rec
    assert rec["source"] == "halftime_pdf"
    assert rec["confirmed_at"] == "2026-11-28T12:00:00+00:00"
    assert "token_hash" not in rec and "deadbeef" not in str(rec)


def test_delete_leads_deletes_matches():
    lead = _lead()
    db = _DB([_Result([lead])])
    assert _run(svc.delete_leads_by_email(db, "qa.coach@example.com")) == 1
    assert db.deleted == [lead] and db.flushed


def test_delete_leads_dry_run_deletes_nothing():
    db = _DB([_Result([_lead()])])
    assert _run(svc.delete_leads_by_email(db, "qa.coach@example.com", dry_run=True)) == 1
    assert db.deleted == [] and not db.flushed


def test_certificate_lists_deleted_leads_only_when_any():
    pr = _pr()
    with_leads = svc.render_certificate(certificate_id="C1", request=pr,
                                        summary={"halftime_leads_deleted": 1})
    assert "Halftime Sheet PDF sign-up records deleted" in with_leads
    none = svc.render_certificate(certificate_id="C1", request=pr, summary={"halftime_leads_deleted": 0})
    assert "Halftime Sheet PDF" not in none and "No matching records" in none


# ── router: export ────────────────────────────────────────────────────────────
def test_export_endpoint_returns_requester_leads_for_verified_request():
    db = _DB([_Result(_pr(request_type="access")), _Result([_lead()])])
    out = _run(router.export_request_data("22222222-2222-2222-2222-222222222222", user=_ADMIN, db=db))
    assert out["data"]["email"] == "qa.coach@example.com"
    assert len(out["data"]["halftime_pdf_leads"]) == 1


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_export_endpoint_refuses_unverified_request(status):
    db = _DB([_Result(_pr(request_type="access", status=status))])
    with pytest.raises(HTTPException) as exc:
        _run(router.export_request_data("x", user=_ADMIN, db=db))
    assert exc.value.status_code == 409
    assert len(db.queries) == 1  # never looked up the leads


def test_export_endpoint_404_for_unknown_request():
    db = _DB([_Result(None)])
    with pytest.raises(HTTPException) as exc:
        _run(router.export_request_data("x", user=_ADMIN, db=db))
    assert exc.value.status_code == 404


# ── router: deletion ──────────────────────────────────────────────────────────
def test_lead_only_preview_needs_no_org_and_writes_nothing():
    db = _DB([_Result(_pr()), _Result([_lead()])])
    out = _run(router.preview_fulfillment("x", router.FulfillIn(), user=_ADMIN, db=db))
    assert out["preview"]["halftime_leads_deleted"] == 1
    assert out["preview"]["players_deleted"] == 0
    assert db.deleted == [] and db.rolled_back


def test_lead_only_deletion_deletes_lead_and_certifies(monkeypatch):
    sent = []

    async def cert(to, name, html_):
        sent.append((to, html_))
    monkeypatch.setattr(router.email_service, "send_deletion_certificate", cert)
    pr = _pr()
    lead = _lead()
    db = _DB([_Result(pr), _Result([lead])])
    out = _run(router.fulfill_request("x", router.FulfillIn(), user=_ADMIN, db=db))
    assert out["status"] == "completed"
    assert out["summary"]["halftime_leads_deleted"] == 1
    assert db.deleted == [lead] and db.committed
    assert "halftime PDF leads deleted=1" in pr.resolution_note
    assert sent and "Halftime Sheet PDF sign-up records deleted" in sent[0][1]


def test_student_ids_without_org_still_refused():
    db = _DB([_Result(_pr())])
    with pytest.raises(HTTPException) as exc:
        _run(router.fulfill_request("x", router.FulfillIn(roster_player_ids=["p1"]), user=_ADMIN, db=db))
    assert exc.value.status_code == 400
    assert db.deleted == [] and not db.committed


def test_org_deletion_also_deletes_requester_leads(monkeypatch):
    calls = {}

    async def fake_exec(db, org, players, games, dry_run=False):
        calls["org"] = org
        return {"players_deleted": 1, "events_scrubbed": 0, "archive_plays_scrubbed": 0,
                "games_deleted": 0, "per_player": [], "dry_run": dry_run}
    monkeypatch.setattr(router.svc, "execute_deletion", fake_exec)

    async def cert(*_a):
        return None
    monkeypatch.setattr(router.email_service, "send_deletion_certificate", cert)
    lead = _lead()
    db = _DB([_Result(_pr(organization_id="o1")), _Result([lead])])
    out = _run(router.fulfill_request("x", router.FulfillIn(roster_player_ids=["p1"]), user=_ADMIN, db=db))
    assert calls["org"] == "o1"
    assert out["summary"]["players_deleted"] == 1
    assert out["summary"]["halftime_leads_deleted"] == 1
    assert db.deleted == [lead]
