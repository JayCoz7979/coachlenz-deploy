"""Finding #21: batch/child writes must verify the caller-supplied parent IDs
belong to the caller's org (events bulk, clip assignments, playlist clips)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import events as ev
from backend.routers import assignments as asg
from backend.routers import playlists as pl


class _Result:
    def __init__(self, v):
        self.v = v

    def scalar_one_or_none(self):
        return self.v

    def scalars(self):
        items = self.v if isinstance(self.v, list) else ([] if self.v is None else [self.v])
        return SimpleNamespace(all=lambda: items)


class _DB:
    def __init__(self, results):
        self._r = list(results)
        self.added = []

    async def execute(self, *_a, **_k):
        return self._r.pop(0)

    def add(self, o):
        self.added.append(o)

    def add_all(self, objs):
        self.added.extend(objs)

    async def commit(self):
        return None

    async def refresh(self, o):
        if not getattr(o, "id", None):
            o.id = "new"


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


# ── events bulk ───────────────────────────────────────────────────────────────
def test_bulk_events_rejects_unowned_game():
    body = [ev.EventCreate(game_id="g_foreign", event_type="play")]
    db = _DB([_Result([])])  # no owned game matches
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ev.bulk_create_events(body, user=_user(), db=db))
    assert exc.value.status_code == 404


def test_bulk_events_accepts_owned_games():
    body = [ev.EventCreate(game_id="g1", event_type="play"),
            ev.EventCreate(game_id="g1", event_type="play")]
    db = _DB([_Result(["g1"])])  # g1 owned
    out = asyncio.run(ev.bulk_create_events(body, user=_user(), db=db))
    assert out["created"] == 2 and len(db.added) == 2


# ── clip assignment ───────────────────────────────────────────────────────────
def test_assignment_rejects_unowned_clip():
    body = asg.AssignmentCreate(clip_id="c_foreign", assigned_to="u2")
    db = _DB([_Result(None)])  # clip not owned
    with pytest.raises(HTTPException) as exc:
        asyncio.run(asg.create_assignment(body, user=_user(), db=db))
    assert exc.value.status_code == 404


def test_assignment_rejects_assignee_outside_org():
    body = asg.AssignmentCreate(clip_id="c1", assigned_to="u_foreign")
    db = _DB([_Result("c1"), _Result(None)])  # clip ok, assignee not in org
    with pytest.raises(HTTPException) as exc:
        asyncio.run(asg.create_assignment(body, user=_user(), db=db))
    assert exc.value.status_code == 404


def test_assignment_accepts_owned_clip_and_org_assignee():
    body = asg.AssignmentCreate(clip_id="c1", assigned_to="u2")
    db = _DB([_Result("c1"), _Result("u2")])
    out = asyncio.run(asg.create_assignment(body, user=_user(), db=db))
    assert "id" in out and len(db.added) == 1


# ── playlist clip ─────────────────────────────────────────────────────────────
def test_playlist_add_clip_rejects_unowned_clip():
    body = pl.PlaylistClipAdd(clip_id="c_foreign")
    db = _DB([_Result(SimpleNamespace(id="pl1")), _Result(None)])  # playlist ok, clip not
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pl.add_clip("pl1", body, user=_user(), db=db))
    assert exc.value.status_code == 404


def test_playlist_add_clip_accepts_owned_clip():
    body = pl.PlaylistClipAdd(clip_id="c1")
    db = _DB([_Result(SimpleNamespace(id="pl1")), _Result("c1")])
    out = asyncio.run(pl.add_clip("pl1", body, user=_user(), db=db))
    assert out["ok"] is True and len(db.added) == 1
