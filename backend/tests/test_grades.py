"""
Track 5.3 - Player Grades Board: parse/aggregate/sheet/CSV (pure) + the annotation
endpoint (DB stub).
"""
import asyncio
import csv
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.grades import (
    parse_grade_letter, points_to_letter, extract_player_grades,
    aggregate_grades, build_grade_sheet, grade_sheet_to_csv, GRADE_CSV_COLUMNS,
)
from backend.routers import grades as grades_router


def _event(eid, play_type, player_grades):
    return SimpleNamespace(id=eid, play_type=play_type, extra_data={"player_grades": player_grades})


SAMPLE = [
    _event("e1", "Pass", [{"jersey": "55", "unit": "OL", "grade": "B - held the pocket"},
                          {"jersey": "7", "unit": "QB", "grade": "A"}]),
    _event("e2", "Run", [{"jersey": "55", "unit": "OL", "grade": "D - lost leverage"},
                         {"jersey": "07", "unit": "QB", "grade": "C"}]),  # 07 == 7
]


# ── pure ─────────────────────────────────────────────────────────────────────
def test_parse_grade_letter():
    assert parse_grade_letter("B - held the pocket") == "B"
    assert parse_grade_letter("a") == "A"
    assert parse_grade_letter("great play") is None   # not letter-first
    assert parse_grade_letter(None) is None


def test_points_to_letter():
    assert points_to_letter(4.0) == "A"
    assert points_to_letter(3.0) == "B"
    assert points_to_letter(1.0) == "D"
    assert points_to_letter(0.0) == "F"


def test_extract_normalizes_jersey_and_reads_grades():
    rows = extract_player_grades(SAMPLE)
    # 4 graded player-plays; 07 collapses to 7.
    assert len(rows) == 4
    qbs = [r for r in rows if r["unit"] == "QB"]
    assert {r["jersey"] for r in qbs} == {"7"}   # 7 and 07 both -> 7


def test_aggregate_by_player_position_and_type():
    agg = aggregate_grades(extract_player_grades(SAMPLE), roster_names={"55": "Big Ol", "7": "QB1"})
    # #55: B(3) + D(1) -> avg 2.0 -> "C"
    assert agg["by_player"]["55"]["avg_points"] == 2.0
    assert agg["by_player"]["55"]["letter"] == "C"
    assert agg["by_player"]["55"]["name"] == "Big Ol"
    assert "OL" in agg["by_position_group"] and "QB" in agg["by_position_group"]
    assert set(agg["by_play_type"]) == {"Pass", "Run"}


def test_grade_sheet_has_all_required_sections():
    sheet = build_grade_sheet(extract_player_grades(SAMPLE), roster_names={"55": "Big Ol"})
    # roster rows, play-type columns, grade cells, and position-group averages.
    assert {p["jersey"] for p in sheet["players"]} == {"55", "7"}
    assert sheet["play_types"] == ["Pass", "Run"]
    assert sheet["cells"]["55"]["Pass"]["letter"] == "B"
    assert "OL" in sheet["position_group_averages"]
    assert "55" in sheet["player_averages"]


def test_grade_sheet_csv_schema():
    sheet = build_grade_sheet(extract_player_grades(SAMPLE), roster_names={"55": "Big Ol"})
    parsed = list(csv.reader(io.StringIO(grade_sheet_to_csv(sheet))))
    assert parsed[0] == GRADE_CSV_COLUMNS + ["Pass", "Run", "overall"]
    assert any("Position group averages" in row for row in parsed)


# ── annotation endpoint ──────────────────────────────────────────────────────
class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


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

    async def refresh(self, _o):
        return None


def _coach():
    return SimpleNamespace(id="c1", organization_id="o1")


def test_annotation_requires_valid_play():
    body = grades_router.AnnotationIn(game_id="g1", event_id="bad", note="nice")
    db = _FakeDB([_Result(SimpleNamespace(id="g1", team_id="t1")),  # game found
                  _Result(None)])                                   # event not found
    with pytest.raises(HTTPException) as exc:
        asyncio.run(grades_router.add_annotation(body, coach=_coach(), db=db))
    assert exc.value.status_code == 404


def test_annotation_linked_to_play_clip():
    body = grades_router.AnnotationIn(game_id="g1", event_id="e1", jersey="07", note="  good hand placement  ")
    db = _FakeDB([_Result(SimpleNamespace(id="g1", team_id="t1")),   # game
                  _Result(SimpleNamespace(id="e1"))])                # event found
    out = asyncio.run(grades_router.add_annotation(body, coach=_coach(), db=db))
    assert out["event_id"] == "e1"          # attached to the play
    assert out["jersey"] == "7"             # normalized
    assert out["note"] == "good hand placement"
    assert db.added and db.added[0].note == "good hand placement"
