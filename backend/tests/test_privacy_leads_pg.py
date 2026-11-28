"""Real-Postgres: halftime_pdf_leads in the privacy export + deletion flows (Stage 2 round 2, LOW 2).

Skipped unless MIGRATIONS_TEST_DATABASE_URL is set (same switch as the 065/067 tests).
Applies every migration to a scratch schema, inserts two fictional leads, then drives
the real admin router functions: export returns only the requester's lead (matched
case-insensitively, token_hash never included), and a lead-only deletion removes that
row and leaves the other one alone. No email is sent (the certificate send is captured).
"""
import os
import uuid
from types import SimpleNamespace

import pytest

_URL = os.environ.get("MIGRATIONS_TEST_DATABASE_URL")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not _URL, reason="MIGRATIONS_TEST_DATABASE_URL is not set")]


def _pg(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _sa(url: str) -> str:
    return _pg(url).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def session():
    import asyncpg
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from backend.migrate import MIGRATIONS_DIR

    conn = await asyncpg.connect(_pg(_URL))
    try:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(f.read_text(encoding="utf-8"))
    finally:
        await conn.close()

    engine = create_async_engine(_sa(_URL))
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


async def _seed(session, status="verified"):
    from sqlalchemy import text
    for name, email in (("Test Coach", "qa.coach@example.com"), ("Other Coach", "other.coach@example.com")):
        await session.execute(text(
            "INSERT INTO halftime_pdf_leads (name, email, consent_text, status, token_hash, confirmed_ip) "
            "VALUES (:n, :e, 'consent', 'confirmed', :h, '203.0.113.8')"),
            {"n": name, "e": email, "h": uuid.uuid4().hex * 2})
    rid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO privacy_requests (id, request_type, requester_name, requester_email, relationship, "
        "student_name, status, status_token) VALUES (:id, 'deletion', 'Test Coach', 'QA.Coach@Example.com', "
        "'other', 'n/a', :st, 'tok')"), {"id": rid, "st": status})
    await session.commit()
    return str(rid)


_ADMIN = SimpleNamespace(email="admin@example.com")


async def test_export_returns_only_requester_lead(session):
    from backend.routers import privacy as router
    rid = await _seed(session)
    out = await router.export_request_data(rid, user=_ADMIN, db=session)
    leads = out["data"]["halftime_pdf_leads"]
    assert [l["email"] for l in leads] == ["qa.coach@example.com"]
    assert leads[0]["confirmed_ip"] == "203.0.113.8"
    assert "token_hash" not in leads[0]


async def test_export_refused_before_verification(session):
    from fastapi import HTTPException
    from backend.routers import privacy as router
    rid = await _seed(session, status="pending")
    with pytest.raises(HTTPException) as exc:
        await router.export_request_data(rid, user=_ADMIN, db=session)
    assert exc.value.status_code == 409


async def test_lead_only_deletion_removes_only_requester_lead(session, monkeypatch):
    from sqlalchemy import text
    from backend.routers import privacy as router
    sent = []

    async def cert(to, name, html_):
        sent.append(to)
    monkeypatch.setattr(router.email_service, "send_deletion_certificate", cert)

    rid = await _seed(session)
    prev = await router.preview_fulfillment(rid, router.FulfillIn(), user=_ADMIN, db=session)
    assert prev["preview"]["halftime_leads_deleted"] == 1
    assert (await session.execute(text("SELECT count(*) FROM halftime_pdf_leads"))).scalar() == 2

    out = await router.fulfill_request(rid, router.FulfillIn(), user=_ADMIN, db=session)
    assert out["summary"]["halftime_leads_deleted"] == 1
    remaining = (await session.execute(text("SELECT email FROM halftime_pdf_leads"))).scalars().all()
    assert remaining == ["other.coach@example.com"]
    status = (await session.execute(text("SELECT status FROM privacy_requests WHERE id = :i"),
                                    {"i": uuid.UUID(rid)})).scalar()
    assert status == "completed"
    assert sent == ["QA.Coach@Example.com"]
