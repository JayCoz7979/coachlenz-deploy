"""Finding #22: the unauthenticated local file endpoints must fail closed in
production, so a regressed R2 config can't turn them into an open object store."""
import asyncio

import pytest
from fastapi import HTTPException

import backend.routers.files as files


def test_serve_404s_in_production_even_if_local_mode_is_on(monkeypatch):
    # Simulate R2 creds regressing in prod: _use_local() True, ENVIRONMENT prod.
    monkeypatch.setattr(files, "_use_local", lambda: True)
    monkeypatch.setattr(files.settings, "ENVIRONMENT", "production")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(files.local_serve("games/other-org/x/film.mp4"))
    assert exc.value.status_code == 404


def test_upload_404s_in_production_even_if_local_mode_is_on(monkeypatch):
    monkeypatch.setattr(files, "_use_local", lambda: True)
    monkeypatch.setattr(files.settings, "ENVIRONMENT", "production")

    class _Req:
        async def body(self):
            return b"x"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(files.local_upload("games/other-org/x/film.mp4", _Req()))
    assert exc.value.status_code == 404


def test_serve_works_in_dev_local_mode(monkeypatch):
    monkeypatch.setattr(files, "_use_local", lambda: True)
    monkeypatch.setattr(files.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(files, "read_local_file", lambda key: b"data")
    out = asyncio.run(files.local_serve("games/o1/x/film.mp4"))
    assert out.body == b"data"


def test_serve_404s_when_local_disabled(monkeypatch):
    # R2 configured (normal prod/dev): local endpoints inert.
    monkeypatch.setattr(files, "_use_local", lambda: False)
    monkeypatch.setattr(files.settings, "ENVIRONMENT", "development")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(files.local_serve("games/o1/x/film.mp4"))
    assert exc.value.status_code == 404
