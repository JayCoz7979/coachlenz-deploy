"""Regression tests for large film uploads.

Production uploads died at exactly 300s because the browser posted the whole file
through the API and Railway's edge closed the request. The game row and the trial
slot were created before any byte arrived, so each failure left an empty game and
spent the trial.

These tests run against the local storage stand-in (no R2, no network): a file
larger than the single-request cap completes in chunks, an interrupted upload
resumes, and a failed or abandoned upload leaves no game and does not reserve a
trial slot.
"""
import asyncio
import inspect
import uuid
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.models.game import Game
from backend.routers import files as files_router
from backend.routers.games import GameCreate, create_game
from backend.routers.upload import upload_file_proxy
from backend.services import film_upload, multipart_store as store
from backend.services import r2
from backend.services.film_upload import (
    SINGLE_REQUEST_LIMIT,
    abort_upload,
    accept_relayed_part,
    finish_upload,
    sign_parts,
    start_upload,
)
from backend.services.trial import reserve_trial_game_slot


class _Result:
    def __init__(self, db):
        self._db = db
        self.rowcount = 1

    def scalar_one(self):
        # Student-data consent is present, so the upload gates get past it.
        return 1

    def scalar_one_or_none(self):
        games = [obj for obj in self._db.added if isinstance(obj, Game)]
        return games[-1] if games else None


class MemDB:
    """Records inserts. Consent lookups report a recorded attestation, and the
    trial UPDATE reports one row so the real reserve helper accepts it."""

    def __init__(self):
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        return _Result(self)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _org():
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_trial=True,
        trial_ends_at=None,
        trial_games_used=0,
        subscription_tier="trial",
        chosen_sports=["football"],
        stripe_subscription_status=None,
    )


def _user(org):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=org.id,
        email_verified=True,
        role="owner",
    )


def _body(size, name="game.mp4"):
    return GameCreate(
        title="Broken Bow vs Sallisaw",
        sport="football",
        file_name=name,
        file_size_bytes=size,
        opponent="Sallisaw",
        duration_seconds=3420,
    )


def _games(db):
    return [obj for obj in db.added if isinstance(obj, Game)]


@pytest.fixture
def local_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(r2, "LOCAL_STORAGE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def reserve_calls(monkeypatch):
    calls = []
    real = reserve_trial_game_slot

    async def spy(db, org):
        calls.append(str(org.id))
        return await real(db, org)

    monkeypatch.setattr(film_upload, "reserve_trial_game_slot", spy)
    return calls


def _files_client():
    app = FastAPI()
    app.include_router(files_router.router)
    return TestClient(app)


def _put(client, url, data: bytes):
    parsed = urlparse(url)
    res = client.put(f"{parsed.path}?{parsed.query}", content=data)
    assert res.status_code == 200, res.text
    return res


def _request(content_length: int) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload/file",
        "raw_path": b"/upload/file",
        "query_string": b"",
        "headers": [(b"content-length", str(content_length).encode())],
        "client": ("203.0.113.8", 1234),
        "server": ("test", 80),
    }
    return Request(scope)


@pytest.mark.unit
def test_proxy_rejects_a_body_over_the_single_request_limit():
    # The legacy one-shot route must fail before it touches the database or storage.
    # Railway closes that request at 300s; the cap sits far enough under it that a
    # slow home connection still finishes.
    assert film_upload.DEFAULT_PART_SIZE <= SINGLE_REQUEST_LIMIT
    film_upload.enforce_proxy_limit(str(SINGLE_REQUEST_LIMIT))  # exactly the cap is allowed

    class BoomDB:
        async def execute(self, *_a, **_k):
            raise AssertionError("oversized proxy upload touched the database")

    fn = inspect.unwrap(upload_file_proxy)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(
            game_id="unused",
            request=_request(SINGLE_REQUEST_LIMIT + 1),
            file=None,
            user=SimpleNamespace(id="u"),
            org=SimpleNamespace(id="o"),
            db=BoomDB(),
        ))
    assert exc.value.status_code == 413
    assert "chunk" in exc.value.detail.lower()


@pytest.mark.unit
def test_upload_larger_than_single_request_limit_completes_in_chunks_and_resumes(local_disk, reserve_calls):
    # One byte over the proxy cap. With the production part size this is two chunks,
    # and neither chunk is posted as one giant API body.
    data = b"f" * (SINGLE_REQUEST_LIMIT + 1)
    assert len(data) > SINGLE_REQUEST_LIMIT
    org, user, db = _org(), None, MemDB()
    user = _user(org)
    started = asyncio.run(start_upload(db, user, org, _body(len(data))))
    assert started["part_count"] >= 2
    assert started["part_size"] <= SINGLE_REQUEST_LIMIT
    assert _games(db) == []
    assert reserve_calls == []

    part_size = started["part_size"]
    chunks = [
        data[i:i + part_size]
        for i in range(0, len(data), part_size)
    ]
    assert len(chunks) == started["part_count"]
    client = _files_client()
    token = started["upload_token"]

    # Interrupt after the first chunk. Finishing now must not create a game or
    # spend the trial, and the stored chunk has to still be there to resume.
    first = sign_parts(org, token, [1], "http://testserver")
    _put(client, first["parts"][0]["url"], chunks[0])
    with pytest.raises(HTTPException) as incomplete:
        asyncio.run(finish_upload(db, user, org, token, _body(len(data))))
    assert incomplete.value.status_code == 409
    assert _games(db) == []
    assert reserve_calls == []
    assert "trial game was not used" in incomplete.value.detail

    # Resume: the status endpoint reports the chunk already stored, and only the
    # missing ones are sent.
    status = film_upload.upload_status(org, token)
    have = {p["part_number"] for p in status["parts"]}
    assert have == {1}
    missing = [n for n in range(1, started["part_count"] + 1) if n not in have]
    signed = sign_parts(org, token, missing, "http://testserver")
    for part in signed["parts"]:
        _put(client, part["url"], chunks[part["part_number"] - 1])

    done = asyncio.run(finish_upload(db, user, org, token, _body(len(data))))
    assert done["status"] == "processing"
    games = _games(db)
    assert len(games) == 1
    assert games[0].r2_key == started["key"]
    assert games[0].file_size_bytes == len(data)
    assert games[0].title == "Broken Bow vs Sallisaw"
    assert games[0].duration_seconds == 3420
    assert reserve_calls == [str(org.id)]
    assert db.commits == 1
    assert r2.read_local_file(started["key"]) == data

    # The multipart id is gone after assemble. Status still reports the film as
    # stored so a retry finishes the game instead of sending the bytes again.
    after = film_upload.upload_status(org, token)
    assert after["assembled"] is True
    assert after["bytes_received"] == len(data)

    # Completing again returns the same game and does not reserve a second slot.
    again = asyncio.run(finish_upload(db, user, org, token, _body(len(data))))
    assert again["id"] == done["id"]
    assert reserve_calls == [str(org.id)]
    assert len(_games(db)) == 1


@pytest.mark.unit
def test_abandoned_or_failed_upload_leaves_no_game_and_no_trial_slot(local_disk, reserve_calls):
    org = _org()
    user = _user(org)
    db = MemDB()
    # Small on purpose: the failure is "never finished", not the file size.
    size = 1500
    started = asyncio.run(start_upload(db, user, org, _body(size), part_size=800))
    store.write_part(started["key"], film_upload.read_session(started["upload_token"], org)["upid"], 1, b"a" * 800)

    # Abandoned: chunks exist, complete was never called.
    assert _games(db) == []
    assert reserve_calls == []

    # Explicit cancel drops the chunks and still does not touch the trial.
    abort_upload(org, started["upload_token"])
    with pytest.raises(HTTPException) as gone:
        asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(size)))
    assert gone.value.status_code == 400
    assert _games(db) == []
    assert reserve_calls == []

    # Storage finished, but the trial slot is already gone. No game is inserted.
    started2 = asyncio.run(start_upload(db, user, org, _body(size), part_size=800))
    session = film_upload.read_session(started2["upload_token"], org)
    store.write_part(session["key"], session["upid"], 1, b"b" * 800)
    store.write_part(session["key"], session["upid"], 2, b"c" * 700)

    async def deny(db, org):
        reserve_calls.append("denied")
        return False

    # Patch only for this call. The earlier spy was installed by the fixture;
    # replace it with a hard deny so the slot is not taken.
    film_upload.reserve_trial_game_slot = deny
    try:
        with pytest.raises(HTTPException) as denied:
            asyncio.run(finish_upload(db, user, org, started2["upload_token"], _body(size)))
    finally:
        film_upload.reserve_trial_game_slot = reserve_trial_game_slot
    assert denied.value.status_code == 403
    assert "trial game was not used" in denied.value.detail
    assert _games(db) == []
    assert db.commits == 0


@pytest.mark.unit
def test_over_20gb_is_rejected_before_any_storage_or_game(local_disk, monkeypatch, reserve_calls):
    def boom(*_a, **_k):
        raise AssertionError("oversized upload reached storage")

    monkeypatch.setattr(store, "create_upload", boom)
    org, user, db = _org(), None, MemDB()
    user = _user(org)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(start_upload(db, user, org, _body(film_upload.max_upload_bytes() + 1)))
    assert exc.value.status_code == 413
    assert _games(db) == []
    assert reserve_calls == []


@pytest.mark.unit
def test_create_game_does_not_insert_a_row_or_reserve_a_trial(local_disk, monkeypatch, reserve_calls):
    def boom(*_a, **_k):
        raise AssertionError("POST /games touched storage")

    monkeypatch.setattr(store, "create_upload", boom)
    org = _org()
    user = _user(org)
    db = MemDB()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_game(body=_body(1000), user=user, org=org, db=db))
    assert exc.value.status_code == 409
    assert _games(db) == []
    assert reserve_calls == []
    assert db.commits == 0


@pytest.mark.unit
def test_relay_accepts_one_chunk_and_rejects_a_body_over_the_part(local_disk):
    org = _org()
    user = _user(org)
    db = MemDB()
    started = asyncio.run(start_upload(db, user, org, _body(1500), part_size=800))
    token = started["upload_token"]
    session = film_upload.read_session(token, org)
    ok = accept_relayed_part(org, token, 1, b"r" * 800)
    assert ok["size"] == 800
    parts = store.list_parts(session["key"], session["upid"])
    assert [p["part_number"] for p in parts] == [1]
    with pytest.raises(HTTPException) as exc:
        accept_relayed_part(org, token, 1, b"r" * 801)
    assert exc.value.status_code == 413
    assert _games(db) == []
