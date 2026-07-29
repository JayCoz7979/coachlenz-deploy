"""
Track 2.1 - play-level CSV export schema.

plays_to_csv is pure (accepts any objects with the Event attributes), so this
exercises the exact column contract and field mapping without a database.
"""
import csv
import io
from types import SimpleNamespace

import pytest

from backend.services.report_export import plays_to_csv, CSV_COLUMNS


def _ev(**kw):
    base = dict(down=None, distance=None, formation=None, personnel=None,
                play_type=None, result=None, blitz=None, coverage=None,
                player=None, time_seconds=None, extra_data={})
    base.update(kw)
    return SimpleNamespace(**base)


def _rows(csv_text):
    return list(csv.reader(io.StringIO(csv_text)))


@pytest.mark.unit
def test_csv_header_matches_schema():
    rows = _rows(plays_to_csv([]))
    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 1  # header only when there are no plays


@pytest.mark.unit
def test_csv_row_maps_every_field():
    ev = _ev(down=3, distance=7, formation="Gun Trips", personnel="11",
             play_type="Pass", result="Complete", blitz="Zero", coverage="Cover 1",
             player="12", time_seconds=125.0,
             extra_data={"pass_concept": "Mesh", "confidence": 0.91,
                         "players": [{"jersey": "12"}, {"jersey": "88"}]})
    header, row = _rows(plays_to_csv([ev]))
    d = dict(zip(header, row))
    assert d["play_number"] == "1"
    assert d["down"] == "3" and d["distance"] == "7"
    assert d["formation"] == "Gun Trips" and d["personnel"] == "11"
    assert d["play_type"] == "Pass" and d["result"] == "Complete"
    assert d["concept"] == "Mesh"                 # pass_concept
    assert d["blitz"] == "Zero" and d["coverage"] == "Cover 1"
    assert d["jersey_numbers"] == "12;88"         # joined from extra_data.players
    assert d["confidence_score"] == "0.91"
    assert d["timestamp"] == "2:05"               # 125s -> m:ss


@pytest.mark.unit
def test_csv_run_concept_and_jersey_fallback():
    ev = _ev(player="7", time_seconds=None,
             extra_data={"run_concept": "Power", "players": []})
    header, row = _rows(plays_to_csv([ev]))
    d = dict(zip(header, row))
    assert d["concept"] == "Power"                # run_concept when no pass_concept
    assert d["jersey_numbers"] == "7"             # falls back to Event.player
    assert d["timestamp"] == ""                   # None -> blank
    assert d["confidence_score"] == ""            # missing -> blank


@pytest.mark.unit
def test_csv_play_numbers_are_sequential():
    rows = _rows(plays_to_csv([_ev(), _ev(), _ev()]))
    assert [r[0] for r in rows[1:]] == ["1", "2", "3"]
