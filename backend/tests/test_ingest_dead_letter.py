"""
Unit tests for IngestWorker.on_dead_letter: when an ingest job is finally given up
on (e.g. the worker was OOM-killed mid-handle), the game must be marked 'error' so
the UI stops spinning — but a game that already finished or already errored must
never be clobbered.
"""
import asyncio
from unittest.mock import patch

import pytest

import backend.workers.worker_ingest as wi
from backend.workers.worker_ingest import IngestWorker


class _Game:
    def __init__(self, status):
        self.status = status
        self.error_message = None


class _DB:
    def __init__(self, game):
        self.game = game
        self.committed = False

    async def get(self, _model, _pk):
        return self.game

    async def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_a):
        return False


def _run(game, payload=None):
    db = _DB(game)
    with patch.object(wi, "AsyncSessionLocal", lambda: _Ctx(db)):
        asyncio.run(IngestWorker().on_dead_letter(payload if payload is not None else {"game_id": "g1"}, "OOM killed"))
    return db


@pytest.mark.unit
@pytest.mark.parametrize("stuck", ["queued", "downloading", "processing"])
def test_dead_letter_marks_stuck_game_error(stuck):
    g = _Game(stuck)
    db = _run(g)
    assert g.status == "error"
    assert "OOM" in (g.error_message or "")
    assert db.committed


@pytest.mark.unit
@pytest.mark.parametrize("terminal", ["ready", "error"])
def test_dead_letter_does_not_clobber_terminal(terminal):
    g = _Game(terminal)
    db = _run(g)
    assert g.status == terminal
    assert not db.committed


@pytest.mark.unit
def test_dead_letter_no_game_id_is_noop():
    g = _Game("processing")
    _run(g, payload={})
    assert g.status == "processing"  # returned before touching the DB
