"""Real-Postgres tests for migration 067 (halftime_pdf_leads) + SqlLeadStore.

Skipped unless MIGRATIONS_TEST_DATABASE_URL is set (same switch as the 065 tests).
Applies every top-level migration to a scratch schema, then drives the real double
opt-in flow through SqlLeadStore: pending -> confirmed, token single use enforced by
the atomic UPDATE, expired token refused, status CHECK and lower(email) uniqueness.
No email is sent (the two outbound calls are captured).
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

_URL = os.environ.get("MIGRATIONS_TEST_DATABASE_URL")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not _URL, reason="MIGRATIONS_TEST_DATABASE_URL is not set")]


def _pg(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _sa(url: str) -> str:
    return _pg(url).replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def session(monkeypatch):
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


@pytest.fixture
def outbox(monkeypatch):
    from backend.services import halftime_leads as svc
    sent = {"confirm": [], "pdf": []}

    async def confirm(to, name, url):
        sent["confirm"].append(url)
        return True

    async def pdf(to, name):
        sent["pdf"].append(to)
        return True

    async def mx(domain):
        return True
    monkeypatch.setattr(svc, "_send_confirmation_email", confirm)
    monkeypatch.setattr(svc, "_send_pdf_email", pdf)
    monkeypatch.setattr(svc, "domain_accepts_mail", mx)
    return sent


async def test_pending_to_confirmed_on_real_postgres(session, outbox):
    from sqlalchemy import text
    from backend.services import halftime_leads as svc

    store = svc.SqlLeadStore(session)
    await svc.submit_lead(store, name="Test Coach", email="QA.Coach@Example.com", phone=None,
                          consent=True, ip="203.0.113.7")
    row = (await session.execute(text(
        "SELECT status, source, email, token_hash, token_expires_at - confirmation_sent_at AS ttl "
        "FROM halftime_pdf_leads"))).one()
    assert row.status == "pending" and row.source == "halftime_pdf"
    assert row.email == "qa.coach@example.com"
    assert row.ttl == timedelta(hours=24)
    token = outbox["confirm"][0].split("token=", 1)[1]
    assert row.token_hash == svc.hash_token(token) and token not in row.token_hash
    assert outbox["pdf"] == []

    await svc.confirm_lead(store, token=token, ip="203.0.113.9")
    row = (await session.execute(text(
        "SELECT status, confirmed_at, confirmed_ip, token_used_at, pdf_sent_at FROM halftime_pdf_leads"))).one()
    assert row.status == "confirmed" and row.confirmed_ip == "203.0.113.9"
    assert row.confirmed_at is not None and row.token_used_at is not None and row.pdf_sent_at is not None
    assert outbox["pdf"] == ["qa.coach@example.com"]

    with pytest.raises(svc.LeadError) as e:
        await svc.confirm_lead(store, token=token, ip="203.0.113.9")
    assert e.value.code == "token_used"
    assert outbox["pdf"] == ["qa.coach@example.com"]


async def test_claim_token_is_atomic_and_respects_expiry(session, outbox):
    from backend.services import halftime_leads as svc

    store = svc.SqlLeadStore(session)
    await svc.submit_lead(store, name="Test Coach", email="qa2@example.com", phone=None, consent=True, ip=None)
    token = outbox["confirm"][0].split("token=", 1)[1]
    lead = await store.get_by_token_hash(svc.hash_token(token))
    now = datetime.now(timezone.utc)
    # Expired at the DB level: the UPDATE refuses.
    assert await store.claim_token(lead, lead.token_hash, now + timedelta(hours=25)) is False
    assert await store.claim_token(lead, lead.token_hash, now) is True
    assert await store.claim_token(lead, lead.token_hash, now) is False   # second click
    await session.commit()


async def test_status_check_and_email_uniqueness(session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    await session.execute(text(
        "INSERT INTO halftime_pdf_leads (name, email, consent_text) VALUES ('A', 'dup@example.com', 'v1')"))
    await session.commit()
    with pytest.raises(IntegrityError):
        await session.execute(text(
            "INSERT INTO halftime_pdf_leads (name, email, consent_text) VALUES ('B', 'DUP@example.com', 'v1')"))
    await session.rollback()
    with pytest.raises(IntegrityError):
        await session.execute(text(
            "INSERT INTO halftime_pdf_leads (name, email, consent_text, status) VALUES ('C', 'c@example.com', 'v1', 'sent')"))
    await session.rollback()
