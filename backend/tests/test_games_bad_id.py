"""Round 3: /games/<id> with an id that is not a UUID answers 404, not 500.

asyncpg raised DataError (a 500) for ids like "abc" or a short prefix, and the
game page then showed an empty main area. The DB must not even be queried.
"""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.base import get_db
from backend.routers import games
from backend.services.auth import get_current_user


class _Result:
    def scalar_one_or_none(self):
        return None


class _DB:
    def __init__(self):
        self.queries = 0

    async def execute(self, *_a, **_k):
        self.queries += 1
        return _Result()


def _client(db):
    app = FastAPI()
    app.include_router(games.router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1", organization_id="org-1")
    return TestClient(app)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["abc", "df42236a", "x" * 36, "urn:uuid:" + str(uuid.UUID(int=1)), "{" + str(uuid.UUID(int=1)) + "}"])
def test_a_non_uuid_game_id_is_404_without_a_query(bad):
    db = _DB()
    client = _client(db)
    for method in ("get", "delete"):
        res = getattr(client, method)(f"/games/{bad}")
        assert res.status_code == 404 and res.json()["detail"] == "Game not found"
    res = client.patch(f"/games/{bad}", json={"title": "t"})
    assert res.status_code == 404
    assert db.queries == 0


@pytest.mark.unit
def test_a_well_formed_unknown_game_id_is_still_the_same_404():
    db = _DB()
    client = _client(db)
    res = client.get(f"/games/{uuid.uuid4()}")
    assert res.status_code == 404 and res.json()["detail"] == "Game not found"
    assert db.queries == 1
