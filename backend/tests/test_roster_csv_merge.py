"""Finding #5: a CSV re-upload must coalesce, not clobber. A trimmed re-upload
(jersey + first name only) previously NULLed out last_name / position /
grade_year on every returning player — silent loss of FERPA-protected data."""
import asyncio
from types import SimpleNamespace

from backend.routers import roster as roster_router


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def scalar(self):
        return self.value

    def scalars(self):
        items = self.value if isinstance(self.value, list) else ([] if self.value is None else [self.value])
        return SimpleNamespace(all=lambda: items)


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.added = []

    async def execute(self, *_a, **_k):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


def _existing_player():
    return SimpleNamespace(jersey_number="7", first_name="Sam", last_name="Rivers",
                           position="QB", grade_year="2026")


def test_trimmed_reupload_preserves_unspecified_fields():
    p = _existing_player()
    db = _FakeDB([_Result(SimpleNamespace(id="t1")),  # _team_or_404
                  _Result(1),                          # assert_student_consent (present)
                  _Result([p])])                       # _roster (existing player #7)
    # CSV supplies only jersey + a corrected first name; last/pos/grade blank.
    body = roster_router.CsvIn(csv="No,First\n7,Samuel\n")
    out = asyncio.run(roster_router.upload_roster_csv("t1", body, user=_user(), db=db))

    assert out["updated"] == 1
    assert p.first_name == "Samuel"    # provided -> updated
    assert p.last_name == "Rivers"     # blank in CSV -> PRESERVED (was the bug)
    assert p.position == "QB"          # preserved
    assert p.grade_year == "2026"      # preserved
    assert db.added == []              # no new player inserted


def test_full_reupload_still_updates_every_field():
    p = _existing_player()
    db = _FakeDB([_Result(SimpleNamespace(id="t1")), _Result(1), _Result([p])])
    body = roster_router.CsvIn(csv="No,First,Last,Pos,Grade\n7,Samuel,Rivera,WR,2027\n")
    out = asyncio.run(roster_router.upload_roster_csv("t1", body, user=_user(), db=db))

    assert out["updated"] == 1
    assert (p.first_name, p.last_name, p.position, p.grade_year) == ("Samuel", "Rivera", "WR", "2027")
