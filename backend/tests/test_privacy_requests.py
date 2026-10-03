"""COPPA/FERPA deletion: the scoped erasure must delete the player and de-identify
ONLY that jersey on that team's plays (keeping the plays), and the certificate must
report exactly what was done."""
import asyncio
from types import SimpleNamespace

from backend.services import privacy_requests as svc


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
        self.deleted = []
        self.flushed = False

    async def execute(self, *_a, **_k):
        return self._r.pop(0)

    async def delete(self, o):
        self.deleted.append(o)

    async def flush(self):
        self.flushed = True


def _player():
    return SimpleNamespace(id="p1", organization_id="o1", team_id="t1",
                           jersey_number="23", first_name="Jordan", last_name="Smith")


def _event(player, extra):
    return SimpleNamespace(player=player, extra_data=extra, game_id="g1", organization_id="o1")


def test_deletion_deletes_player_and_deidentifies_only_that_jersey():
    ev_match = _event("23", {"primary_player_jersey": "23",
                             "players": [{"jersey": "23"}, {"jersey": "10"}]})
    # Call order per execute_deletion: player lookup, game-ids for team, events for jersey.
    db = _DB([
        _Result(_player()),        # RosterPlayer lookup
        _Result(["g1"]),           # Game.id for the team
        _Result([ev_match]),       # Events on those games with player == "23"
    ])
    summary = asyncio.run(svc.execute_deletion(db, "o1", ["p1"], []))

    assert summary["players_deleted"] == 1
    assert summary["events_scrubbed"] == 1
    assert summary["games_deleted"] == 0
    # The play row survives but the student is no longer identified.
    assert ev_match.player is None
    assert ev_match.extra_data["primary_player_jersey"] is None
    assert ev_match.extra_data["players"] == [{"jersey": "10"}]  # teammate untouched
    assert db.deleted and getattr(db.deleted[0], "id", None) == "p1"
    assert db.flushed


def test_deletion_skips_unknown_player_no_write():
    db = _DB([_Result(None)])  # player not found / not in org
    summary = asyncio.run(svc.execute_deletion(db, "o1", ["ghost"], []))
    assert summary == {"players_deleted": 0, "events_scrubbed": 0, "games_deleted": 0, "per_player": []}
    assert not db.deleted


def test_certificate_reports_only_what_happened():
    req = SimpleNamespace(requester_name="Pat Smith", relationship="parent",
                          student_name="Jordan Smith", created_at=None)
    html = svc.render_certificate(
        certificate_id="CL-DEL-20261002-abcd1234", request=req,
        summary={"players_deleted": 1, "events_scrubbed": 5, "games_deleted": 0})
    assert "CL-DEL-20261002-abcd1234" in html
    assert "Roster / player profile records deleted" in html
    assert "de-identified on <strong>5</strong> plays" in html
    assert "Game film deleted" not in html  # none deleted -> not claimed
    assert "Jordan Smith" in html


def test_certificate_handles_nothing_found():
    req = SimpleNamespace(requester_name="Pat", relationship="parent",
                          student_name="Nobody", created_at=None)
    html = svc.render_certificate(
        certificate_id="CL-DEL-X", request=req,
        summary={"players_deleted": 0, "events_scrubbed": 0, "games_deleted": 0})
    assert "No matching records were found" in html
