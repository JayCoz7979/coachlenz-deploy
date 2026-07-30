"""
The coach-notes section is appended to a report's section spec only when the coach
flagged plays, and stays ahead of the trailing Scout's Note transparency section.
Pure section-spec assembly — no LLM call.
"""
from backend.services.report_writer import (
    _maybe_coach_notes,
    _coach_notes_spec,
    COACH_NOTES_INSIGHT,
)


def test_inserts_before_trailing_scouts_note():
    spec = [{"heading": "Executive Summary", "insight_type": "tendency"},
            {"heading": "Scout's Note: Confidence", "insight_type": "tendency"}]
    _maybe_coach_notes(spec, {"coach_flagged_plays": [{"clock": "0:10", "note": "x"}]})
    assert [s["heading"] for s in spec] == [
        "Executive Summary", "Coach's Flagged Plays & Notes", "Scout's Note: Confidence"]
    assert spec[1]["insight_type"] == COACH_NOTES_INSIGHT


def test_appends_at_end_without_scouts_note():
    spec = [{"heading": "Executive Summary", "insight_type": "tendency"}]
    _maybe_coach_notes(spec, {"coach_flagged_plays": [1]})
    assert spec[-1]["insight_type"] == COACH_NOTES_INSIGHT


def test_no_section_when_nothing_flagged():
    spec = [{"heading": "Executive Summary", "insight_type": "tendency"}]
    _maybe_coach_notes(spec, {})
    assert len(spec) == 1
    _maybe_coach_notes(spec, {"coach_flagged_plays": []})
    assert len(spec) == 1


def test_spec_references_the_data_key_and_verbatim_rule():
    spec = _coach_notes_spec()
    assert spec["insight_type"] == COACH_NOTES_INSIGHT
    assert "coach_flagged_plays" in spec["instructions"]
    assert "VERBATIM" in spec["instructions"]
