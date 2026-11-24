"""Round 4: one shared rule turns a non-UUID game id into 404 on every route.

Harriet's round 4 list: ai_detect x7, grades x4, the roster lookup, and
/events?game_id= and /clips?game_id= all answered 500 (asyncpg DataError) for
"abc". The app-wide dependency in backend/game_ids.py answers 404 "Game not
found" before any query. accuracy and coverage also 404 for a game that does
not exist, instead of 200 "ready: false".
"""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import main
from backend.game_ids import is_game_id, is_invalid_uuid_error
from backend.models.base import get_db
from backend.services.auth import get_current_user

HARRIET_GETS = [
    "/games/{g}/accuracy", "/games/{g}/tendencies", "/games/{g}/coverage",
    "/games/{g}/auto-detect/status", "/games/{g}/players", "/games/{g}/agent-log",
    "/games/{g}/runs",
    "/grades/game/{g}", "/grades/game/{g}/sheet", "/grades/game/{g}/export",
    "/grades/game/{g}/annotations",
    "/rosters/resolve/game/{g}",
    "/events?game_id={g}", "/clips?game_id={g}",
]
BAD = ["abc", "df42236a", "x" * 36, "' OR 1=1--", "{" + str(uuid.UUID(int=7)) + "}"]


class _Result:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return SimpleNamespace(all=lambda: [])

    def all(self):
        return []


class _DB:
    def __init__(self):
        self.queries = 0

    async def execute(self, *_a, **_k):
        self.queries += 1
        return _Result()


@pytest.fixture
def client():
    db = _DB()

    async def _db():
        yield db

    user = SimpleNamespace(id="u1", organization_id="org-1", role="head_coach",
                           is_platform_admin=False, email="qa+u1@coachlenz.com")
    main.app.dependency_overrides[get_db] = _db
    main.app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(main.app, raise_server_exceptions=False), db
    finally:
        main.app.dependency_overrides.clear()


def _route_path(template: str) -> str:
    if not template.startswith("/rosters"):
        return template
    prefix = [r.path for r in main.app.routes if isinstance(r, APIRoute) and r.path.endswith("/resolve/game/{game_id}")]
    return prefix[0].replace("{game_id}", "{g}")


@pytest.mark.unit
@pytest.mark.parametrize("template", HARRIET_GETS)
@pytest.mark.parametrize("bad", BAD)
def test_harriets_routes_answer_404_for_a_non_uuid_id_without_a_query(client, template, bad):
    c, db = client
    from urllib.parse import quote
    res = c.get(_route_path(template).replace("{g}", quote(bad, safe="")))
    assert res.status_code == 404, (template, bad, res.status_code, res.text[:200])
    assert res.json()["detail"] == "Game not found"
    assert db.queries == 0


@pytest.mark.unit
def test_every_route_with_a_game_id_path_param_is_covered(client):
    c, db = client
    checked = 0
    for route in main.app.routes:
        if not isinstance(route, APIRoute) or "{game_id}" not in route.path:
            continue
        path = route.path.replace("{game_id}", "abc")
        for other in ("{archive_id}", "{id}", "{play_id}", "{event_id}"):
            path = path.replace(other, str(uuid.uuid4()))
        for method in route.methods:
            res = c.request(method, path)
            assert res.status_code == 404, (method, route.path, res.status_code)
            checked += 1
    assert checked >= 20  # 21 method and path pairs at round 4
    assert db.queries == 0


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/games/{g}/accuracy", "/games/{g}/coverage"])
def test_accuracy_and_coverage_404_for_a_game_that_does_not_exist(client, path):
    c, db = client
    res = c.get(path.replace("{g}", str(uuid.uuid4())))
    assert res.status_code == 404 and res.json()["detail"] == "Game not found"
    assert db.queries == 1  # the org-scoped game lookup, nothing after it


@pytest.mark.unit
def test_an_empty_clips_filter_keeps_its_old_meaning(client):
    c, _ = client
    assert c.get("/clips?game_id=").status_code != 404


@pytest.mark.unit
def test_valid_uuid_forms_pass_the_shape_check():
    u = uuid.uuid4()
    for ok in (str(u), u.hex, str(u).upper()):
        assert is_game_id(ok)
    for bad in BAD + ["", None, 123]:
        assert not is_game_id(bad)


class DataError(Exception):
    pass


@pytest.mark.unit
def test_backstop_maps_only_an_invalid_uuid_data_error_to_404():
    from sqlalchemy.exc import DBAPIError
    bad_uuid = DBAPIError("SELECT 1", {}, DataError(
        "invalid input for query argument $1: 'abc' (invalid UUID 'abc': length must be between 32..36 characters, got 3)"))
    other = DBAPIError("SELECT 1", {}, DataError("value too long for type character varying(5)"))
    assert is_invalid_uuid_error(bad_uuid)
    assert not is_invalid_uuid_error(other)
    req = SimpleNamespace(method="POST", url=SimpleNamespace(path="/games/x/runs/abc/restore"))
    res = asyncio.run(main._invalid_uuid_handler(req, bad_uuid))
    assert res.status_code == 404 and b"Not found" in res.body and b"abc" not in res.body
    with pytest.raises(DBAPIError):
        asyncio.run(main._invalid_uuid_handler(req, other))
