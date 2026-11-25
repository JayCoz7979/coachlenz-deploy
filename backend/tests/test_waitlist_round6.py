"""A second unsubscribe must not 500, and it must not rewrite the first opt-out.

One suppression row per address. GET never changes state. POST and the admin
route set unsubscribed_at once. suppressed_at and reason stay at that first write.
"""
import asyncio
import os
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.routers import admin as admin_router
from backend.routers import auth as auth_router
from backend.routers import funnel as funnel_router
from backend.services import waitlist_email as mail

MIG = pathlib.Path(__file__).resolve().parents[1] / "migrations"


@pytest.mark.unit
def test_suppression_insert_is_on_conflict():
    stmt = mail.suppression_statement("Coach@School.edu", datetime(2026, 11, 24), "unsubscribe_link")
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (email_sha256)" in sql
    assert "suppressed_at" in sql


class _Result:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []


class _DB:
    def __init__(self):
        self.queries = 0

    async def execute(self, *_a, **_k):
        self.queries += 1
        return _Result()

    async def commit(self):
        pass


def _app(db):
    app = FastAPI()
    app.state.limiter = limiter

    async def _db():
        yield db

    app.include_router(auth_router.router)
    app.dependency_overrides[get_db] = _db
    return app


@pytest.mark.unit
def test_one_click_post_and_get_return_200_twice():
    from fastapi.testclient import TestClient
    limiter.reset()
    client = TestClient(_app(_DB()))
    token = "a" * 43
    for method in ("post", "get"):
        first = getattr(client, method)("/auth/unsubscribe", **(
            {"json": {"token": token}} if method == "post" else {"params": {"token": token}}
        ))
        second = getattr(client, method)("/auth/unsubscribe", **(
            {"json": {"token": token}} if method == "post" else {"params": {"token": token}}
        ))
        assert first.status_code == second.status_code == 200
        assert first.json()["ok"] is True and second.json()["ok"] is True
        if method == "get":
            assert first.json()["already_unsubscribed"] is False


_URL = os.environ.get(
    "UPLOAD_TEST_DATABASE_URL",
    "postgresql+asyncpg://coachlenz:coachlenz@localhost:5432/coachlenz_upload_test",
)


@pytest.mark.integration
def test_rejoin_then_one_click_and_admin_unsubscribe_on_postgres():
    import asyncpg

    raw = _URL.replace("postgresql+asyncpg://", "postgresql://", 1)

    async def admin(sql):
        conn = await asyncpg.connect(raw)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    try:
        asyncio.run(admin("SELECT 1"))
    except Exception as exc:
        if os.environ.get("CI"):
            pytest.fail(f"Postgres is required in CI ({type(exc).__name__})")
        pytest.skip(f"Postgres is not reachable ({type(exc).__name__})")

    dbname = "unsub6_" + uuid.uuid4().hex[:10]
    url = raw.rsplit("/", 1)[0] + "/" + dbname
    asyncio.run(admin(f'CREATE DATABASE "{dbname}"'))
    asyncio.run(admin(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') "
        "THEN CREATE ROLE postgres; END IF; END $$"))
    env = dict(os.environ, DATABASE_URL=url)
    migrated = subprocess.run(
        [sys.executable, "-m", "backend.migrate"],
        cwd=str(MIG.parents[1]), env=env, capture_output=True, text=True, timeout=300,
    )
    assert migrated.returncode == 0, migrated.stderr[-2000:]

    async def scenario():
        engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://", 1))
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(auth_router.router)
        app.include_router(funnel_router.router)
        app.include_router(admin_router.router)

        async def _db():
            async with Session() as session:
                yield session

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[admin_router.require_unsubscribe_admin] = lambda: object()
        limiter.reset()
        email = f"qa+r6-{uuid.uuid4().hex[:8]}@school.edu"
        lead_body = {
            "email": email,
            "first_name": "Ada",
            "role": "head_coach",
            "source": "coachlenz-app-waitlist",
        }

        async def state():
            conn = await asyncpg.connect(url)
            try:
                return await conn.fetchrow(
                    "SELECT unsubscribed_at, unsubscribe_token FROM marketing_leads WHERE lower(email) = lower($1)",
                    email,
                )
            finally:
                await conn.close()

        async def suppression_count():
            conn = await asyncpg.connect(url)
            try:
                return await conn.fetchval("SELECT count(*) FROM email_suppressions")
            finally:
                await conn.close()

        async def event_count(address):
            conn = await asyncpg.connect(url)
            try:
                return await conn.fetchval(
                    "SELECT count(*) FROM marketing_consent_events "
                    "WHERE lower(email) = lower($1) AND event_type = 'unsubscribed'",
                    address,
                )
            finally:
                await conn.close()

        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post("/leads", json=lead_body, headers={"user-agent": "Round6"})
                assert created.status_code == 200, created.text
                row = await state()
                token = row["unsubscribe_token"]
                assert row["unsubscribed_at"] is None and token

                preview = await client.get("/auth/unsubscribe", params={"token": token})
                assert preview.status_code == 200
                assert preview.json()["already_unsubscribed"] is False
                assert (await state())["unsubscribed_at"] is None
                assert await event_count(email) == 0

                first = await client.post("/auth/unsubscribe", json={"token": token})
                second = await client.post("/auth/unsubscribe", json={"token": token})
                assert first.status_code == second.status_code == 200
                assert (await state())["unsubscribed_at"] is not None
                assert await suppression_count() == 1
                assert await event_count(email) == 1

                again = await client.get("/auth/unsubscribe", params={"token": token})
                assert again.status_code == 200
                assert again.json()["already_unsubscribed"] is True
                assert await event_count(email) == 1

                rejoined = await client.post("/leads", json=lead_body, headers={"user-agent": "Round6"})
                assert rejoined.status_code == 200
                assert (await state())["unsubscribed_at"] is None

                after = await client.post("/auth/unsubscribe", json={"token": token})
                assert after.status_code == 200
                assert (await state())["unsubscribed_at"] is not None

                await client.post("/leads", json=lead_body, headers={"user-agent": "Round6"})
                assert (await state())["unsubscribed_at"] is None
                admin_first = await client.post("/admin/leads/unsubscribe", json={"email": email.upper()})
                admin_second = await client.post("/admin/leads/unsubscribe", json={"email": email})
                assert admin_first.status_code == admin_second.status_code == 200
                assert admin_first.json()["updated"] is True
                assert admin_second.json()["updated"] is False
                assert (await state())["unsubscribed_at"] is not None
                assert await suppression_count() == 1
                # The first one-click wrote the suppression. reason stays that value.
                conn = await asyncpg.connect(url)
                try:
                    reason = await conn.fetchval("SELECT reason FROM email_suppressions")
                finally:
                    await conn.close()
                assert reason == "unsubscribe_link"

                race_email = f"qa+r6-race-{uuid.uuid4().hex[:8]}@school.edu"
                raced = await client.post("/leads", json={**lead_body, "email": race_email}, headers={"user-agent": "Round6"})
                assert raced.status_code == 200

                async def one_admin():
                    async with Session() as session:
                        return await admin_router.unsubscribe_lead_by_email(
                            admin_router.EmailUnsubscribe(email=race_email), object(), session)

                results = await asyncio.gather(*[one_admin() for _ in range(8)])
                assert sum(1 for item in results if item["updated"] is True) == 1
                assert await event_count(race_email) == 1

                token_email = f"qa+r6-token-{uuid.uuid4().hex[:8]}@school.edu"
                token_created = await client.post(
                    "/leads", json={**lead_body, "email": token_email}, headers={"user-agent": "Round6"})
                assert token_created.status_code == 200
                conn = await asyncpg.connect(url)
                try:
                    token_row = await conn.fetchrow(
                        "SELECT unsubscribe_token FROM marketing_leads WHERE lower(email) = lower($1)",
                        token_email,
                    )
                finally:
                    await conn.close()

                async def one_token():
                    async with Session() as session:
                        return await auth_router._unsubscribe_by_token(session, token_row["unsubscribe_token"])

                token_results = await asyncio.gather(*[one_token() for _ in range(8)])
                assert all(item["ok"] is True for item in token_results)
                assert await event_count(token_email) == 1
        finally:
            await engine.dispose()

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(admin(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
