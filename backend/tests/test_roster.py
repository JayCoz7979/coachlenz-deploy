"""
Track 3.3 - roster management + jersey-to-player resolution.

The parsing/normalization/resolution logic is pure and tested directly; a few
endpoint behaviors (404 / 409 / game resolve) are driven with a DB stub.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.roster import parse_roster_csv, normalize_jersey, resolve_jersey
from backend.routers import roster as roster_router


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_normalize_jersey():
    assert normalize_jersey("07") == "7"       # leading zero dropped
    assert normalize_jersey(" 7 ") == "7"
    assert normalize_jersey(23) == "23"
    assert normalize_jersey("GK") == "GK"      # non-numeric kept as-is
    assert normalize_jersey(None) == ""


def test_parse_roster_csv_maps_aliased_headers_and_skips_incomplete():
    csv_text = (
        "No,First,Last,Pos,Grade\n"
        "7,Sam,Rivers,QB,2026\n"
        "88,Alex,Kim,WR,2027\n"
        ",Noname,NoJersey,RB,2026\n"   # no jersey -> skipped
        "12,,Blank,DB,2025\n"          # no first name -> skipped
    )
    players = parse_roster_csv(csv_text)
    assert [p["jersey_number"] for p in players] == ["7", "88"]
    assert players[0] == {"jersey_number": "7", "first_name": "Sam", "last_name": "Rivers",
                          "position": "QB", "grade_year": "2026"}


def test_parse_roster_csv_requires_jersey_and_first_name_columns():
    with pytest.raises(ValueError):
        parse_roster_csv("name,team\nSam,Eagles\n")


def test_resolve_jersey_normalizes_both_sides():
    roster = [SimpleNamespace(jersey_number="7", first_name="Sam"),
              SimpleNamespace(jersey_number="88", first_name="Alex")]
    assert resolve_jersey(roster, "07").first_name == "Sam"   # 07 -> 7
    assert resolve_jersey(roster, 88).first_name == "Alex"
    assert resolve_jersey(roster, "99") is None


# ── endpoint stubs ───────────────────────────────────────────────────────────
class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        items = self.value if isinstance(self.value, list) else ([] if self.value is None else [self.value])
        return SimpleNamespace(all=lambda: items)


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *_a, **_k):
        return self._results.pop(0)

    async def commit(self):
        return None


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


def test_list_roster_team_not_found_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(roster_router.list_roster("t1", user=_user(), db=_FakeDB([_Result(None)])))
    assert exc.value.status_code == 404


def test_add_player_duplicate_jersey_409():
    db = _FakeDB([_Result(SimpleNamespace(id="t1")),          # team lookup
                  _Result(SimpleNamespace(id="p_existing"))])  # jersey already present
    body = roster_router.PlayerIn(jersey_number="07", first_name="Sam")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(roster_router.add_player("t1", body, user=_user(), db=db))
    assert exc.value.status_code == 409


def test_resolve_game_maps_jerseys_to_players():
    game = SimpleNamespace(id="g1", team_id="t1", organization_id="o1")
    roster = [SimpleNamespace(id="p1", jersey_number="12", first_name="Sam", last_name="R",
                              position="QB", grade_year="2026", is_active=True)]
    events = [SimpleNamespace(player="12", extra_data={"players": [{"jersey": "88"}]}),
              SimpleNamespace(player="99", extra_data={})]
    db = _FakeDB([_Result(game), _Result(roster), _Result(events)])
    out = asyncio.run(roster_router.resolve_game_jerseys("g1", user=_user(), db=db))
    by_jersey = {l["jersey_number"]: l["player"] for l in out["links"]}
    assert set(by_jersey) == {"12", "88", "99"}
    assert by_jersey["12"]["first_name"] == "Sam"   # linked
    assert by_jersey["88"] is None                  # not on roster
    assert by_jersey["99"] is None


def test_resolve_game_without_team_returns_hint():
    game = SimpleNamespace(id="g1", team_id=None, organization_id="o1")
    out = asyncio.run(roster_router.resolve_game_jerseys("g1", user=_user(), db=_FakeDB([_Result(game)])))
    assert out["links"] == [] and out["team_id"] is None
