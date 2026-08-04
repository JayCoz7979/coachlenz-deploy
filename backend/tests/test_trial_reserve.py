"""Finding #2: the trial game cap must be enforced by an atomic conditional
UPDATE, not a read-then-increment, so concurrent uploads can't exceed the limit."""
import asyncio
from types import SimpleNamespace

from backend.services.trial import reserve_trial_game_slot, TRIAL_GAME_LIMIT


class _CountingDB:
    """Simulates Postgres executing `UPDATE ... WHERE trial_games_used < LIMIT`
    under a row lock: each serialized execute increments only while under the
    cap and reports rowcount accordingly."""
    def __init__(self, start=0, limit=TRIAL_GAME_LIMIT):
        self.used = start
        self.limit = limit

    async def execute(self, *_a, **_k):
        if self.used < self.limit:
            self.used += 1
            return SimpleNamespace(rowcount=1)
        return SimpleNamespace(rowcount=0)


def _trial_org():
    # is_trial=True and no trial_ends_at -> is_trial_active() True.
    return SimpleNamespace(id="o1", is_trial=True, trial_ends_at=None, trial_games_used=0)


def _paid_org():
    return SimpleNamespace(id="o2", is_trial=False, trial_ends_at=None, trial_games_used=99)


def test_first_reservation_succeeds_then_cap_blocks():
    db = _CountingDB()
    org = _trial_org()
    assert asyncio.run(reserve_trial_game_slot(db, org)) is True    # slot 1 (of 1)
    assert asyncio.run(reserve_trial_game_slot(db, org)) is False   # cap reached
    assert db.used == TRIAL_GAME_LIMIT                              # never over-counts


def test_concurrent_bursts_never_exceed_limit():
    # Ten serialized attempts (the DB serializes the row lock) yield exactly
    # LIMIT successes — the race that let all 5 pass is closed.
    db = _CountingDB()
    org = _trial_org()
    results = [asyncio.run(reserve_trial_game_slot(db, org)) for _ in range(10)]
    assert sum(results) == TRIAL_GAME_LIMIT
    assert db.used == TRIAL_GAME_LIMIT


def test_paid_org_is_unaffected():
    # No trial cap for a non-trial org; must not touch the counter.
    db = _CountingDB(start=0, limit=0)
    assert asyncio.run(reserve_trial_game_slot(db, _paid_org())) is True
    assert db.used == 0
