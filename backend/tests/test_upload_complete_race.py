"""Complete-race tests against real async Postgres (asyncpg).

SQLite and in-memory fakes do not expire ORM objects on rollback, so they cannot
see the MissingGreenlet that asyncpg sessions raise when finish_upload touches
org.id after await db.rollback(). These tests skip only when no Postgres is
reachable. Set UPLOAD_TEST_DATABASE_URL to point them at a database.
"""
import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.game import Game
from backend.models.job import Job
from backend.models.legal import LegalAcceptance
from backend.models.organization import Organization
from backend.models.team import Team
from backend.models.user import User
from backend.routers.games import GameCreate
from backend.services import r2
from backend.services.film_upload import MSG_TRIAL_AFTER, finish_upload, start_upload
from backend.services.legal import STUDENT_DATA_VERSION
from backend.services.multipart_store import write_part

pytestmark = pytest.mark.integration

_URL = os.environ.get(
    "UPLOAD_TEST_DATABASE_URL",
    "postgresql+asyncpg://coachlenz:coachlenz@localhost:5432/coachlenz_upload_test",
)
_TABLES = [
    Organization.__table__, User.__table__, Team.__table__,
    LegalAcceptance.__table__, Game.__table__, Job.__table__,
]


def _body(name="race.mp4"):
    return GameCreate(title="Race", sport="football", file_name=name, file_size_bytes=1000)


async def _reachable():
    import asyncpg
    raw = _URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(raw)
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()


@pytest.fixture
async def pg(tmp_path, monkeypatch):
    try:
        await _reachable()
    except Exception as exc:
        # GitHub Actions sets CI. There the job must fail if Postgres is down,
        # because these tests are the only check for the async rollback race.
        if os.environ.get("CI"):
            pytest.fail(f"async Postgres is required in CI ({type(exc).__name__})")
        pytest.skip(f"async Postgres is not reachable ({type(exc).__name__})")
    monkeypatch.setattr(r2, "LOCAL_STORAGE_DIR", str(tmp_path))
    engine = create_async_engine(_URL)
    # Match production: commit does not expire, rollback does.
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base_drop(c))
        await conn.run_sync(lambda c: Base_create(c))
    yield Session
    await engine.dispose()


def Base_drop(sync_conn):
    from backend.models.base import Base
    Base.metadata.drop_all(sync_conn, tables=list(reversed(_TABLES)))


def Base_create(sync_conn):
    from backend.models.base import Base
    Base.metadata.create_all(sync_conn, tables=_TABLES)


async def _seed(Session, *, trial: bool):
    async with Session() as db:
        org = Organization(
            name="Race HS",
            slug=f"race-{uuid.uuid4().hex[:8]}",
            is_trial=trial,
            trial_games_used=0,
            chosen_sports=["football"],
            subscription_tier="trial" if trial else "coach",
        )
        db.add(org)
        await db.flush()
        db.add(LegalAcceptance(
            organization_id=org.id,
            document="student_data",
            version=STUDENT_DATA_VERSION,
        ))
        await db.commit()
        org_id = org.id
    return org_id


def _user(org_id):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=org_id, email_verified=True)


async def _prepared(Session, org_id):
    async with Session() as db:
        org = await db.get(Organization, org_id)
        user = _user(org_id)
        started = await start_upload(db, user, org, _body(), part_size=1000)
        from backend.services.film_upload import read_session
        session = read_session(started["upload_token"], org)
        write_part(session["key"], session["upid"], 1, b"q" * 1000)
        token = started["upload_token"]
    return token


@pytest.mark.asyncio
async def test_reserve_false_on_async_postgres_is_403_not_500(pg, monkeypatch):
    from backend.services import film_upload

    async def deny(db, org):
        return False

    monkeypatch.setattr(film_upload, "reserve_trial_game_slot", deny)
    org_id = await _seed(pg, trial=True)
    token = await _prepared(pg, org_id)
    async with pg() as db:
        org = await db.get(Organization, org_id)
        # The attribute is loaded now. Rollback inside finish_upload must not
        # make a later org.id access lazy-load on this async session.
        assert org.id == org_id
        with pytest.raises(film_upload_http()) as exc:
            await finish_upload(db, _user(org_id), org, token, _body())
    assert exc.value.status_code == 403
    assert exc.value.detail == MSG_TRIAL_AFTER
    from backend.services.film_upload import read_session
    from backend.services.multipart_store import object_size
    key = read_session(token, SimpleNamespace(id=org_id))["key"]
    assert object_size(key) is None
    async with pg() as db:
        from sqlalchemy import select, func
        n = await db.scalar(select(func.count()).select_from(Game).where(Game.organization_id == org_id))
    assert n == 0


def film_upload_http():
    from fastapi import HTTPException
    return HTTPException


@pytest.mark.asyncio
async def test_four_simultaneous_completes_of_one_token_never_500(pg):
    from fastapi import HTTPException

    org_id = await _seed(pg, trial=False)
    token = await _prepared(pg, org_id)

    async def once():
        async with pg() as db:
            org = await db.get(Organization, org_id)
            try:
                return await finish_upload(db, _user(org_id), org, token, _body())
            except HTTPException as exc:
                return exc

    results = await asyncio.gather(*[once() for _ in range(4)])
    ids = []
    for result in results:
        if isinstance(result, HTTPException):
            assert result.status_code == 403, result.detail
            assert result.detail == MSG_TRIAL_AFTER
            continue
        assert isinstance(result, dict), result
        assert result.get("id")
        ids.append(result["id"])
    assert ids, results
    assert len(set(ids)) == 1
    async with pg() as db:
        from sqlalchemy import select, func
        n = await db.scalar(select(func.count()).select_from(Game).where(Game.organization_id == org_id))
    assert n == 1


@pytest.mark.asyncio
async def test_insert_that_loses_the_race_at_flush_returns_the_winning_game(pg, monkeypatch):
    """Round 3: the other complete commits the same key after our existence check.

    The unique r2_key index then fails at flush (the INSERT), not at commit. That
    must return the winner's game, never raise (a raised IntegrityError is a 500).
    """
    from sqlalchemy import select, func
    from backend.services import film_upload

    org_id = await _seed(pg, trial=False)
    token = await _prepared(pg, org_id)
    real = film_upload._existing_game
    state = {"first": True, "winner": None}

    async def racing(db, oid, key):
        if state["first"]:
            state["first"] = False
            async with pg() as other:
                winner = Game(organization_id=oid, title="Winner", sport="football",
                              r2_key=key, status="processing", file_size_bytes=1000)
                other.add(winner)
                await other.commit()
                state["winner"] = str(winner.id)
            return None
        return await real(db, oid, key)

    monkeypatch.setattr(film_upload, "_existing_game", racing)
    async with pg() as db:
        org = await db.get(Organization, org_id)
        result = await finish_upload(db, _user(org_id), org, token, _body())
    assert result["id"] == state["winner"]
    async with pg() as db:
        n = await db.scalar(select(func.count()).select_from(Game).where(Game.organization_id == org_id))
        jobs = await db.scalar(select(func.count()).select_from(Job))
    assert n == 1
    assert jobs == 0  # the loser's ingest job rolled back with its game
