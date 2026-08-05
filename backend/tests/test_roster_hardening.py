"""Findings #18 and #19 for the roster:
  #18 a concurrent add that loses the unique-constraint race returns a clean 409,
     not an unhandled 500.
  #19 clone_roster copies height and weight (was silently dropping them)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.routers import roster as rr


class _Result:
    def __init__(self, v):
        self.v = v

    def scalar_one_or_none(self):
        return self.v

    def scalar_one(self):
        return self.v

    def scalars(self):
        items = self.v if isinstance(self.v, list) else ([] if self.v is None else [self.v])
        return SimpleNamespace(all=lambda: items)


class _DB:
    def __init__(self, results, commit_error=None):
        self._r = list(results)
        self.added = []
        self.commit_error = commit_error
        self.rolled = False

    async def execute(self, *_a, **_k):
        return self._r.pop(0)

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rolled = True

    async def refresh(self, o):
        if not getattr(o, "id", None):
            o.id = "new"


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


def test_add_player_race_returns_409_not_500():
    db = _DB([_Result(SimpleNamespace(id="t1")),  # _team_or_404
              _Result(1),                          # consent present
              _Result(None)],                      # pre-check: no existing jersey
             commit_error=IntegrityError("dup", {}, Exception("uq_roster_team_jersey")))
    body = rr.PlayerIn(jersey_number="7", first_name="Sam")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rr.add_player("t1", body, user=_user(), db=db))
    assert exc.value.status_code == 409
    assert db.rolled is True   # rolled back before surfacing the 409


def test_clone_roster_copies_height_and_weight():
    src = [SimpleNamespace(jersey_number="7", first_name="Sam", last_name="R",
                           position="QB", grade_year="2026", height="6'2\"", weight=200)]
    db = _DB([_Result(SimpleNamespace(id="t1")),   # source team
              _Result(SimpleNamespace(id="t2")),   # target team
              _Result(1),                           # consent present
              _Result(src),                         # source roster
              _Result([])])                         # target roster (empty)
    out = asyncio.run(rr.clone_roster("t1", "t2", user=_user(), db=db))
    assert out["cloned"] == 1
    added = db.added[0]
    assert added.height == "6'2\"" and added.weight == 200
