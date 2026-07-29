"""
Track 3.1 - AD usage dashboard: aggregation/CSV/limit helpers (pure) + endpoint
gating and per-coach limit setting (DB stub).
"""
import asyncio
import csv
import io
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.usage import (
    aggregate_usage, usage_to_csv, over_limit, month_start, USAGE_CSV_COLUMNS,
)
from backend.routers import ad


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_month_start():
    ms = month_start(datetime(2026, 7, 29, 15, 42, 9))
    assert ms == datetime(2026, 7, 1, 0, 0, 0, 0)


def test_over_limit_rules():
    assert over_limit(5, 5) is True            # at the cap -> blocked
    assert over_limit(6, 5) is True
    assert over_limit(4, 5) is False
    assert over_limit(100, None) is False      # no cap
    assert over_limit(100, 0) is False         # 0 = unlimited


def test_coach_blocked_when_at_ad_set_limit():
    # This is the decision the analysis trigger makes before queueing a run.
    used, limit = 8, 8
    assert over_limit(used, limit) is True


def test_aggregate_usage_counts():
    rows = [
        {"user_id": "u1", "sport": "football", "analysis_type": "deep"},
        {"user_id": "u1", "sport": "football", "analysis_type": "fast"},
        {"user_id": "u2", "sport": "basketball", "analysis_type": "deep"},
    ]
    agg = aggregate_usage(rows)
    assert agg["total"] == 3
    assert agg["by_coach"] == {"u1": 2, "u2": 1}
    assert agg["by_sport"] == {"football": 2, "basketball": 1}
    assert agg["by_type"] == {"deep": 2, "fast": 1}


def test_usage_csv_schema():
    rows = [{"coach": "Sam", "email": "s@x.com", "sport": "football",
             "analysis_type": "deep", "timestamp": datetime(2026, 7, 2, 9, 0, 0)}]
    parsed = list(csv.reader(io.StringIO(usage_to_csv(rows))))
    assert parsed[0] == USAGE_CSV_COLUMNS
    assert parsed[1][:4] == ["Sam", "s@x.com", "football", "deep"]
    assert parsed[1][4].startswith("2026-07-02")


# ── endpoint gating + limit setting ──────────────────────────────────────────
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


def test_require_ad_account_blocks_non_ad_tier():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ad.require_ad_account(org=SimpleNamespace(subscription_tier="coach")))
    assert exc.value.status_code == 403


def test_require_ad_account_allows_athletic_dept():
    org = SimpleNamespace(subscription_tier="athletic_dept")
    assert asyncio.run(ad.require_ad_account(org=org)) is org


def test_set_limit_rejects_coach_outside_org():
    body = ad.LimitIn(user_id="u9", monthly_run_limit=10)
    db = _FakeDB([_Result(None)])  # user not found in org
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ad.set_limit(body, org=SimpleNamespace(id="o1"), db=db))
    assert exc.value.status_code == 404


def test_set_limit_rejects_negative():
    body = ad.LimitIn(user_id="u1", monthly_run_limit=-3)
    db = _FakeDB([_Result(SimpleNamespace(id="u1"))])  # user found
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ad.set_limit(body, org=SimpleNamespace(id="o1"), db=db))
    assert exc.value.status_code == 422


def test_set_limit_creates_new_limit():
    body = ad.LimitIn(user_id="u1", monthly_run_limit=25)
    db = _FakeDB([_Result(SimpleNamespace(id="u1")),  # user found
                  _Result(None)])                      # no existing limit
    out = asyncio.run(ad.set_limit(body, org=SimpleNamespace(id="o1"), db=db))
    assert out["monthly_run_limit"] == 25
    assert db.added and db.added[0].monthly_run_limit == 25


def test_set_limit_updates_existing():
    existing = SimpleNamespace(monthly_run_limit=5)
    body = ad.LimitIn(user_id="u1", monthly_run_limit=40)
    db = _FakeDB([_Result(SimpleNamespace(id="u1")), _Result(existing)])
    asyncio.run(ad.set_limit(body, org=SimpleNamespace(id="o1"), db=db))
    assert existing.monthly_run_limit == 40
