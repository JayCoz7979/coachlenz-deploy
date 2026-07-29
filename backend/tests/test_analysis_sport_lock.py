"""
Track 1.1 — sport-lock is enforced on the ANALYSIS TRIGGER, not just film import.

The expensive path (deep 3-pass + per-play Opus verify) is queued by
`POST /games/{id}/auto-detect`. A single-sport plan must get a 403 there before a
job is enqueued, so it can never burn deep-analysis COGS on a sport it never
bought (e.g. a legacy/mis-tagged game whose sport is outside the locked plan).

Runs under plain pytest (no pytest-asyncio dependency): the async endpoint is
driven with asyncio.run, and the DB is a minimal stub — the guard fires right
after the game lookup, before any real DB write, so no database is needed.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers.ai_detect import trigger_auto_detect


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Returns the game on the first execute() (the Game lookup); no-ops the rest
    (stale-job cleanup update + commit) so the 'allowed' path can proceed past the
    guard without a real database."""
    def __init__(self, game):
        self._game = game
        self._calls = 0

    async def execute(self, *_a, **_k):
        self._calls += 1
        # First call is the SELECT Game; hand back the game. Later calls are the
        # orphan-cleanup UPDATE / job-existence SELECT — return an empty result.
        return _Result(self._game if self._calls == 1 else None)

    async def commit(self):
        return None


def _game(sport, status="ready"):
    return SimpleNamespace(id="g1", sport=sport, status=status,
                           organization_id="org1")


def _org(chosen_sports):
    return SimpleNamespace(id="org1", chosen_sports=chosen_sports,
                           subscription_tier="starter")


def _user():
    return SimpleNamespace(id="u1", organization_id="org1")


def _trigger(game, org):
    return asyncio.run(trigger_auto_detect(
        game_id="g1", dry_run=False, mode="deep", full=False, test=False,
        grade=False, user=_user(), org=org, db=_FakeDB(game),
    ))


def test_locked_sport_analysis_is_blocked_with_403():
    """Org locked to basketball; football game analysis must 403 (not enqueue)."""
    with pytest.raises(HTTPException) as exc:
        _trigger(_game("football"), _org(["basketball"]))
    assert exc.value.status_code == 403
    assert "Basketball" in exc.value.detail  # names the plan's locked sport


def test_allowed_sport_passes_the_guard():
    """Locked-in sport must NOT 403 at the guard. We set the game to a non-ready
    status so flow stops at the 400 status check AFTER the sport guard — proving
    the guard let the allowed sport through (no false 403)."""
    with pytest.raises(HTTPException) as exc:
        _trigger(_game("basketball", status="uploading"), _org(["basketball"]))
    assert exc.value.status_code == 400  # got PAST sport lock, failed on status
    assert "ready" in exc.value.detail.lower()


def test_unlocked_org_is_not_restricted():
    """Pre-onboarding org (empty chosen_sports) is unrestricted — backward compat.
    Again gated to a non-ready status so we assert the guard did not 403."""
    with pytest.raises(HTTPException) as exc:
        _trigger(_game("football", status="uploading"), _org([]))
    assert exc.value.status_code == 400  # not 403 — no sport restriction applied
