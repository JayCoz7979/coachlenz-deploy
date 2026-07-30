"""
Clip playback URL resolution: URLs are presigned fresh from the parent game film on
every read (never a stored r2_url), so long-lived share links keep playing. Driven
with a DB stub + a monkeypatched presigner (no boto/network).
"""
import asyncio
from types import SimpleNamespace

import backend.services.playback as pb


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.queries = 0

    async def execute(self, *_a, **_k):
        self.queries += 1
        return _Result(self._rows)


def _clip(cid, game_id="g1", title="Clip", start=1.0, end=5.0):
    return SimpleNamespace(id=cid, game_id=game_id, title=title, start_time=start, end_time=end)


def _patch_presigner(monkeypatch, mapping):
    # safe_download_url is imported into the playback module namespace.
    monkeypatch.setattr(pb, "safe_download_url", lambda key, **_k: (f"signed:{key}" if key else None))
    return mapping


def test_clip_playback_presigns_from_parent_game(monkeypatch):
    _patch_presigner(monkeypatch, {})
    clips = [_clip("c1", "g1"), _clip("c2", "g1")]
    db = _FakeDB([("g1", "games/g1/film.mp4")])
    out = asyncio.run(pb.clip_playback(clips, "o1", db))
    # Presigned game film + a #t=start,end media fragment so the link opens at the play.
    assert out[0]["url"] == "signed:games/g1/film.mp4#t=1.0,5.0"
    assert out[0]["start_time"] == 1.0 and out[0]["end_time"] == 5.0
    assert out[0]["game_id"] == "g1"


def test_clip_playback_url_none_when_game_has_no_film(monkeypatch):
    _patch_presigner(monkeypatch, {})
    db = _FakeDB([("g1", None)])
    out = asyncio.run(pb.clip_playback([_clip("c1", "g1")], "o1", db))
    assert out[0]["url"] is None


def test_clip_playback_empty_makes_no_query(monkeypatch):
    _patch_presigner(monkeypatch, {})
    db = _FakeDB([])
    out = asyncio.run(pb.clip_playback([], "o1", db))
    assert out == []
    assert db.queries == 0  # no game ids -> no lookup


def test_game_key_map_skips_lookup_without_ids(monkeypatch):
    db = _FakeDB([])
    out = asyncio.run(pb.game_key_map([None, ""], "o1", db))
    assert out == {}
    assert db.queries == 0
