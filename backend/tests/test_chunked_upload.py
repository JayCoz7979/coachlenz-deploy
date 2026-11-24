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
    from backend.models.job import Job
    jobs = [obj for obj in db.added if isinstance(obj, Job)]
    assert len(jobs) == 1
    assert jobs[0].job_type == "ingest"
    assert jobs[0].payload == {"game_id": str(games[0].id)}
    assert "source_url" not in (jobs[0].payload or {})
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
    assert "chunk" in exc.value.detail.lower()
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


@pytest.mark.unit
def test_retrying_the_same_chunk_overwrites_it_and_then_completes(local_disk, reserve_calls):
    org, user, db = _org(), None, MemDB()
    user = _user(org)
    started = asyncio.run(start_upload(db, user, org, _body(1500), part_size=800))
    session = film_upload.read_session(started["upload_token"], org)
    key, upid = session["key"], session["upid"]
    store.write_part(key, upid, 1, b"x" * 800)
    # The connection died after a partial chunk. The retry sends the whole part again.
    store.write_part(key, upid, 1, b"y" * 800)
    listed = store.list_parts(key, upid)
    assert [(p["part_number"], p["size"]) for p in listed] == [(1, 800)]
    with open(store._part_path(upid, 1), "rb") as fh:
        assert fh.read(1) == b"y"
    store.write_part(key, upid, 2, b"z" * 700)
    done = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1500)))
    assert r2.read_local_file(key) == (b"y" * 800) + (b"z" * 700)
    assert len(_games(db)) == 1
    assert reserve_calls == [str(org.id)]
    assert done["id"]


@pytest.mark.unit
def test_assembled_size_must_match_the_declared_size(local_disk, monkeypatch, reserve_calls):
    org, user, db = _org(), None, MemDB()
    user = _user(org)
    started = asyncio.run(start_upload(db, user, org, _body(1500), part_size=800))
    session = film_upload.read_session(started["upload_token"], org)
    store.write_part(session["key"], session["upid"], 1, b"a" * 800)
    store.write_part(session["key"], session["upid"], 2, b"b" * 700)

    def lie(*_a, **_k):
        return 1500 + 10

    monkeypatch.setattr(store, "complete_upload", lie)
    deleted = []
    monkeypatch.setattr(store, "delete_object", lambda key: deleted.append(key))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1500)))
    assert exc.value.status_code == 413
    assert deleted == [session["key"]]
    assert _games(db) == []
    assert reserve_calls == []


class _OneSlotDB(MemDB):
    """The trial UPDATE succeeds once, then reports rowcount 0. Mirrors the
    conditional UPDATE in reserve_trial_game_slot."""

    def __init__(self):
        super().__init__()
        self.used = 0

    async def execute(self, stmt, *_a, **_k):
        from sqlalchemy.sql.dml import Update
        if isinstance(stmt, Update) and "trial_games_used" in str(stmt):
            if self.used < 1:
                self.used += 1
                return SimpleNamespace(rowcount=1, scalar_one=lambda: 1, scalar_one_or_none=lambda: None)
            return SimpleNamespace(rowcount=0, scalar_one=lambda: 1, scalar_one_or_none=lambda: None)
        # Existence lookups are per object key. The other film must not look
        # like a duplicate of this one, or the second complete would return it.
        return SimpleNamespace(rowcount=1, scalar_one=lambda: 1, scalar_one_or_none=lambda: None)


@pytest.mark.unit
def test_two_uploads_cannot_both_take_the_one_trial_slot(local_disk):
    org, user = _org(), None
    user = _user(org)
    db = _OneSlotDB()
    first = asyncio.run(start_upload(db, user, org, _body(1000, "a.mp4"), part_size=1000))
    second = asyncio.run(start_upload(db, user, org, _body(1000, "b.mp4"), part_size=1000))
    for token, byte in ((first, b"a"), (second, b"b")):
        session = film_upload.read_session(token["upload_token"], org)
        store.write_part(session["key"], session["upid"], 1, byte * 1000)

    ok = asyncio.run(finish_upload(db, user, org, first["upload_token"], _body(1000, "a.mp4")))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(finish_upload(db, user, org, second["upload_token"], _body(1000, "b.mp4")))
    assert exc.value.status_code == 403
    assert len(_games(db)) == 1
    assert _games(db)[0].r2_key == first["key"]
    assert ok["id"] == str(_games(db)[0].id)
    assert db.used == 1


@pytest.mark.unit
def test_duplicate_complete_that_loses_the_insert_race_returns_the_same_game(local_disk, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    org, user = _org(), None
    user = _user(org)
    db = MemDB()
    started = asyncio.run(start_upload(db, user, org, _body(1000), part_size=1000))
    session = film_upload.read_session(started["upload_token"], org)
    store.write_part(session["key"], session["upid"], 1, b"q" * 1000)
    first = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1000)))
    winner = _games(db)[0]

    # The second request passed the "no row yet" check before the first commit
    # became visible, then the unique key rejected its insert.
    async def miss_then_hit(db_, org_id, key):
        if not getattr(db_, "_race_seen", False):
            db_._race_seen = True
            return None
        return winner

    real_commit = db.commit

    async def conflict_once():
        if not getattr(db, "_conflicted", False):
            db._conflicted = True
            raise IntegrityError("INSERT", {}, Exception("games_r2_key_unique"))
        await real_commit()

    async def rollback():
        db.added[:] = [obj for obj in db.added if obj is winner or not isinstance(obj, type(winner))]

    monkeypatch.setattr(film_upload, "_existing_game", miss_then_hit)
    monkeypatch.setattr(db, "commit", conflict_once)
    monkeypatch.setattr(db, "rollback", rollback)
    again = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1000)))
    assert again["id"] == first["id"]
    assert len(_games(db)) == 1


@pytest.mark.unit
def test_local_complete_race_keeps_the_object_and_returns_the_game(local_disk, monkeypatch):
    """Both completes listed the parts. The first assembled and removed them.
    The second complete_upload then raises MultipartError. That used to be a 502.
    The object is already the right size, so the second call returns the game."""
    from backend.services.multipart_store import MultipartError

    org, user, db = _org(), None, MemDB()
    user = _user(org)
    org.is_trial = False
    started = asyncio.run(start_upload(db, user, org, _body(1000), part_size=1000))
    session = film_upload.read_session(started["upload_token"], org)
    store.write_part(session["key"], session["upid"], 1, b"q" * 1000)
    first = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1000)))

    real_list = store.list_parts

    def still_listed(*a, **k):
        try:
            return real_list(*a, **k)
        except MultipartError:
            return [{"part_number": 1, "etag": '"gone"', "size": 1000}]

    monkeypatch.setattr(store, "list_parts", still_listed)
    again = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1000)))
    assert again["id"] == first["id"]
    assert r2.read_local_file(session["key"]) == b"q" * 1000


@pytest.mark.unit
def test_trial_loser_deletes_its_orphan_but_not_another_games_object(local_disk, monkeypatch):
    org, user, db = _org(), None, MemDB()
    user = _user(org)
    started = asyncio.run(start_upload(db, user, org, _body(1000), part_size=1000))
    session = film_upload.read_session(started["upload_token"], org)
    store.write_part(session["key"], session["upid"], 1, b"q" * 1000)
    first = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1000)))
    winner = _games(db)[0]
    deleted = []
    monkeypatch.setattr(store, "delete_object", lambda key: deleted.append(key))

    async def deny(db_, org_):
        return False

    calls = {"n": 0}

    async def miss_then_hit(db_, org_id, key):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return winner

    monkeypatch.setattr(film_upload, "reserve_trial_game_slot", deny)
    monkeypatch.setattr(film_upload, "_existing_game", miss_then_hit)
    again = asyncio.run(finish_upload(db, user, org, started["upload_token"], _body(1000)))
    assert again["id"] == first["id"]
    assert deleted == []


@pytest.mark.unit
def test_presign_rejects_over_20gb_before_touching_the_database():
    from backend.routers.upload import presign_upload, UploadRequest
    import inspect

    class BoomDB:
        async def execute(self, *_a, **_k):
            raise AssertionError("presign touched the database")

    fn = inspect.unwrap(presign_upload)
    body = UploadRequest(
        game_id="g", file_name="huge.mp4",
        file_size_bytes=film_upload.max_upload_bytes() + 1,
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(body, user=SimpleNamespace(id="u"), org=SimpleNamespace(id="o"), db=BoomDB()))
    assert exc.value.status_code == 413


@pytest.mark.unit
def test_link_import_and_live_logger_still_create_their_own_games():
    import inspect
    from backend.routers import ingest, live_game, scout_football

    url_src = inspect.getsource(ingest.ingest_from_url)
    assert "Game(" in url_src
    assert "reserve_trial_game_slot" in url_src
    assert 'job_type="ingest"' in url_src
    assert "source_url" in url_src

    live_src = inspect.getsource(live_game.create_session)
    assert "Game(" in live_src
    assert 'status="live"' in live_src
    assert "reserve_trial_game_slot" not in live_src

    scout_src = inspect.getsource(scout_football.create_session)
    assert "Game(" in scout_src
    assert "reserve_trial_game_slot" not in scout_src
