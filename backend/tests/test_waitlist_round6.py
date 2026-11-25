"""Round 6: a second unsubscribe must not 500 on email_suppressions.

One suppression row per address. Clicking the link again, or unsubscribing
after the lead re-joins, refreshes that row and still opts the lead out.
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

        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post("/leads", json=lead_body, headers={"user-agent": "Round6"})
                assert created.status_code == 200, created.text
                row = await state()
                token = row["unsubscribe_token"]
                assert row["unsubscribed_at"] is None and token

                first = await client.post("/auth/unsubscribe", json={"token": token})
                second = await client.post("/auth/unsubscribe", json={"token": token})
                assert first.status_code == second.status_code == 200
                assert (await state())["unsubscribed_at"] is not None
                assert await suppression_count() == 1

                again = await client.get("/auth/unsubscribe", params={"token": token})
                assert again.status_code == 200

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
                assert (await state())["unsubscribed_at"] is not None
                assert await suppression_count() == 1
        finally:
            await engine.dispose()

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(admin(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
