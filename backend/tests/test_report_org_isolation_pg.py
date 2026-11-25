"""
Two-org report isolation on real Postgres.

The SQLite harness swaps UUID/JSONB/ARRAY and never applies the SQL migrations,
so it cannot catch a check-constraint or array-binding leak. This module runs
only under the Postgres 16 CI job (`pytest -m postgres`) after
`python -m backend.migrate`.

live_game is not exercised here. Migration 001's report_type check is
opponent, self_scout, custom. Including live_game is 065_live_game_report_type.sql
in PR #296, which is not on this branch. Same-org live_game stays in the SQLite suite.
"""
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

from backend.models.base import AsyncSessionLocal, engine
from backend.models.event import Event
from backend.models.game import Game
from backend.models.job import Job
from backend.models.organization import Organization
from backend.models.report import TendencyReport
from backend.models.user import User
from backend.routers import reports as reports_router
from backend.services.auth import create_access_token, hash_password
from backend.workers.worker_reports import (
    GAME_NOT_IN_ORG,
    ReportInputError,
    ReportsWorker,
)

# One event loop for the module. The process-wide async engine keeps pooled
# connections, and a fresh loop per test makes asyncpg raise "attached to a
# different loop" on the second test.
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]

THEIRS = "xq-pg-rival-note-7f3a"


async def test_live_game_skipped_until_migration_065():
    pytest.skip(
        "Skipped on Postgres: migration 001's report_type check does not include "
        "live_game. That change is 065_live_game_report_type.sql in PR #296, which "
        "must ship before or with this PR. Same-org live_game is covered on SQLite."
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(reports_router.router)
    return app


def _token(user_id, org_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id), str(org_id))}"}


async def _counts(org_id) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        reports = await db.scalar(
            select(func.count()).select_from(TendencyReport).where(
                TendencyReport.organization_id == org_id
            )
        )
        jobs = await db.scalar(
            select(func.count()).select_from(Job).where(Job.organization_id == org_id)
        )
        return int(reports or 0), int(jobs or 0)


async def _two_orgs():
    """A paid org, a rival org with a live session and a secret play, and tokens."""
    async with AsyncSessionLocal() as db:
        org_a = Organization(
            name="PG Org A", slug=f"pga-{uuid.uuid4().hex[:8]}", is_trial=False,
        )
        org_b = Organization(
            name="PG Org B", slug=f"pgb-{uuid.uuid4().hex[:8]}", is_trial=False,
        )
        db.add_all([org_a, org_b])
        await db.flush()
        user_a = User(
            organization_id=org_a.id, name="A Owner",
            email=f"a-{uuid.uuid4().hex[:8]}@x.com",
            hashed_password=hash_password("x"), role="owner",
        )
        user_b = User(
            organization_id=org_b.id, name="B Owner",
            email=f"b-{uuid.uuid4().hex[:8]}@x.com",
            hashed_password=hash_password("x"), role="owner",
        )
        # admin_level 'super' is a platform admin in is_platform_admin and is
        # allowed by the migration 001 check. 'platform' is not in that check.
        org_admin = Organization(
            name="PG Platform", slug=f"pgp-{uuid.uuid4().hex[:8]}",
            is_trial=False, admin_level="super",
        )
        db.add(org_admin)
        await db.flush()
        user_admin = User(
            organization_id=org_admin.id, name="Platform",
            email=f"p-{uuid.uuid4().hex[:8]}@x.com",
            hashed_password=hash_password("x"), role="owner",
        )
        own = Game(
            organization_id=org_a.id, title="Our Film", sport="football", status="ready",
        )
        foreign = Game(
            organization_id=org_b.id, title="Rival Live", sport="football", status="live",
        )
        db.add_all([user_a, user_b, user_admin, own, foreign])
        await db.flush()
        secret = Event(
            game_id=foreign.id, organization_id=org_b.id, event_type="play",
            side="offense", player="77", coach_note=THEIRS, is_highlight=True,
        )
        db.add(secret)
        await db.commit()
        return {
            "org_a": org_a.id,
            "org_admin": org_admin.id,
            "own": str(own.id),
            "foreign": str(foreign.id),
            "token_a": _token(user_a.id, org_a.id),
            "token_admin": _token(user_admin.id, org_admin.id),
        }


async def test_cross_org_post_creates_no_report_or_job():
    world = await _two_orgs()
    before = await _counts(world["org_a"])
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as ac:
        r = await ac.post(
            "/reports",
            json={
                "title": "Stolen", "sport": "football",
                "game_ids": [world["foreign"]], "report_type": "opponent",
            },
            headers=world["token_a"],
        )
    assert r.status_code == 404
    assert r.json().get("detail") == "Game not found"
    assert THEIRS not in r.text
    assert await _counts(world["org_a"]) == before


async def test_mixed_own_and_foreign_ids_404_for_paid_org():
    world = await _two_orgs()
    before = await _counts(world["org_a"])
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as ac:
        r = await ac.post(
            "/reports",
            json={
                "title": "Mixed", "sport": "football",
                "game_ids": [world["own"], world["foreign"]],
                "report_type": "opponent",
            },
            headers=world["token_a"],
        )
    assert r.status_code == 404
    assert r.json().get("detail") == "Game not found"
    assert THEIRS not in r.text
    assert await _counts(world["org_a"]) == before


async def test_platform_admin_is_not_exempt():
    world = await _two_orgs()
    before = await _counts(world["org_admin"])
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as ac:
        r = await ac.post(
            "/reports",
            json={
                "title": "Admin Stolen", "sport": "football",
                "game_ids": [world["foreign"]], "report_type": "self_scout",
            },
            headers=world["token_admin"],
        )
    assert r.status_code == 404
    assert THEIRS not in r.text
    assert await _counts(world["org_admin"]) == before


async def test_worker_refuses_foreign_game_without_reading_plays():
    world = await _two_orgs()
    async with AsyncSessionLocal() as db:
        planted = TendencyReport(
            organization_id=world["org_a"],
            game_ids=[world["foreign"]],
            sport="football",
            report_type="opponent",
            title="Planted cross org",
        )
        db.add(planted)
        await db.commit()
        planted_id = planted.id

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        with pytest.raises(ReportInputError, match="not found"):
            await ReportsWorker().handle({"report_id": str(planted_id)})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)

    played = [s for s in statements if "events" in s.lower()]
    assert played == []
    assert all(THEIRS not in s for s in statements)

    async with AsyncSessionLocal() as db:
        row = await db.get(TendencyReport, planted_id)
        note = await db.scalar(
            select(Event.coach_note).where(Event.coach_note == THEIRS)
        )
    assert row is not None
    assert row.generated_at is None
    assert row.summary_json is None
    assert row.error_reason == GAME_NOT_IN_ORG
    assert THEIRS not in (row.error_reason or "")
    assert note == THEIRS
