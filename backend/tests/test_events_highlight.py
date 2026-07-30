"""
Film-room marks: PATCH /events/{id} can star a play as a highlight and attach a
coach note, and the serialized event carries both back. Driven with a DB stub
(get_current_user is bypassed by calling the handler directly).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers.events import update_event, EventUpdate, _event_out


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.committed = False

    async def execute(self, *_a, **_k):
        return self._results.pop(0)

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        return None


def _event(**kw):
    base = dict(id="e1", event_type="play", side="offense", down=1, distance=10,
                formation="Trips", play_type="Pass", defensive_front=None, coverage=None,
                blitz=None, result="Gain", yards_gained=12, personnel="11", motion=False,
                time_seconds=42.0, player="7", is_highlight=False, coach_note=None, extra_data={})
    base.update(kw)
    return SimpleNamespace(**base)


def _user():
    return SimpleNamespace(id="u1", organization_id="o1")


def test_event_out_includes_highlight_and_note():
    out = _event_out(_event(is_highlight=True, coach_note="great read"))
    assert out["is_highlight"] is True
    assert out["coach_note"] == "great read"


def test_mark_highlight():
    ev = _event()
    out = asyncio.run(update_event("e1", EventUpdate(is_highlight=True), user=_user(),
                                   db=_FakeDB([_Result(ev)])))
    assert ev.is_highlight is True
    assert out["is_highlight"] is True


def test_add_and_clear_coach_note():
    ev = _event()
    asyncio.run(update_event("e1", EventUpdate(coach_note="watch the pull guard"),
                             user=_user(), db=_FakeDB([_Result(ev)])))
    assert ev.coach_note == "watch the pull guard"
    # Clearing the note back to empty is a real update (exclude_unset lets "" through).
    out = asyncio.run(update_event("e1", EventUpdate(coach_note=""), user=_user(),
                                   db=_FakeDB([_Result(ev)])))
    assert ev.coach_note == ""
    assert out["coach_note"] == ""


def test_marking_highlight_does_not_touch_other_fields():
    ev = _event(play_type="Pass", yards_gained=12)
    asyncio.run(update_event("e1", EventUpdate(is_highlight=True), user=_user(),
                             db=_FakeDB([_Result(ev)])))
    assert ev.play_type == "Pass" and ev.yards_gained == 12  # untouched


def test_update_missing_event_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_event("missing", EventUpdate(is_highlight=True), user=_user(),
                                 db=_FakeDB([_Result(None)])))
    assert exc.value.status_code == 404
