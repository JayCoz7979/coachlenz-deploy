"""Stage 2 QA on #303 (issue #299): billing fixes. No DB, no network, no live Stripe.

M1  one open $7 Checkout Session per org (row lock + reuse), and a second PAID
    session for an already-unlocked org is flagged for a human refund.
H1  POST /reports with report_type=live_game is behind the same $7 paywall.
L2  outside production: no live Stripe key at startup or checkout, and the webhook
    ignores events whose livemode does not match the environment.

The real-Postgres versions (concurrent tabs, cross-org 404s, H1 with no row written)
are in test_stage2_qa_pg.py.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.routers.billing as billing
import backend.routers.credits as credits_router
import backend.routers.reports as reports_router
from backend.config import settings
from backend.models.billing_event import LiveTrackerExtraPayment
from backend.services import live_tracker as lt
from backend.services import stripe_mode
from backend.tests.test_live_tracker import PAID, _body, _CheckoutDB, _org, _req, _user
from backend.tests.test_stripe_webhook import _call, _event, _live_tracker_session, _sign, _StubDB

pytestmark = pytest.mark.unit

FUTURE = datetime.now(timezone.utc) + timedelta(hours=2)
PAST = datetime.now(timezone.utc) - timedelta(minutes=1)


@pytest.fixture
def priced(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live_tracker")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")


def _stripe(monkeypatch, retrieve=None):
    calls = {"create": 0, "retrieve": []}

    def create(**kw):
        calls["create"] += 1
        return SimpleNamespace(id=f"cs_test_new_{calls['create']}", url="https://checkout.stripe.test/new",
                               expires_at=int(time.time()) + 3600)

    def _retrieve(sid):
        calls["retrieve"].append(sid)
        if isinstance(retrieve, Exception):
            raise retrieve
        return retrieve

    monkeypatch.setattr(billing.stripe.checkout.Session, "create", create)
    monkeypatch.setattr(billing.stripe.checkout.Session, "retrieve", _retrieve)
    return calls


def _checkout(org):
    db = _CheckoutDB(org)
    out = asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(), org=org, db=db))
    return out, db


# ── M1: one open Checkout Session per org ─────────────────────────────────────
def test_checkout_locks_the_org_row_before_deciding(monkeypatch, priced):
    _stripe(monkeypatch)
    _out, db = _checkout(_org())
    lock = db.selects[0]
    assert lock._for_update_arg is not None                      # SELECT ... FOR UPDATE
    assert "FOR UPDATE" in str(lock.compile(dialect=__import__(
        "sqlalchemy.dialects.postgresql", fromlist=["dialect"]).dialect()))


def test_new_checkout_remembers_the_open_session_in_the_same_commit(monkeypatch, priced):
    calls = _stripe(monkeypatch)
    out, db = _checkout(_org())
    assert calls["create"] == 1 and out == {"checkout_url": "https://checkout.stripe.test/new"}
    assert db.updates[-1]["live_tracker_open_session_id"] == "cs_test_new_1"
    assert db.updates[-1]["live_tracker_open_session_expires_at"] is not None
    assert db.commits == 1


def test_second_tab_reuses_the_open_session_and_creates_nothing(monkeypatch, priced):
    open_session = SimpleNamespace(id="cs_test_open", status="open", payment_status="unpaid",
                                   url="https://checkout.stripe.test/open")
    calls = _stripe(monkeypatch, retrieve=open_session)
    org = _org(live_tracker_open_session_id="cs_test_open", live_tracker_open_session_expires_at=FUTURE)
    out, db = _checkout(org)
    assert out == {"checkout_url": "https://checkout.stripe.test/open", "reused": True}
    assert calls["create"] == 0 and calls["retrieve"] == ["cs_test_open"]
    assert db.updates == [] and db.added == [] and db.commits == 0 and db.rollbacks == 1


def test_paid_but_not_yet_granted_session_refuses_instead_of_charging_again(monkeypatch, priced):
    done = SimpleNamespace(id="cs_test_open", status="complete", payment_status="paid", url=None)
    calls = _stripe(monkeypatch, retrieve=done)
    org = _org(live_tracker_open_session_id="cs_test_open", live_tracker_open_session_expires_at=FUTURE)
    with pytest.raises(HTTPException) as exc:
        _checkout(org)
    assert exc.value.status_code == 409 and "already being processed" in exc.value.detail
    assert calls["create"] == 0


@pytest.mark.parametrize("retrieved,expires", [
    (SimpleNamespace(id="cs_old", status="expired", payment_status="unpaid", url=None), FUTURE),
    (RuntimeError("stripe down"), FUTURE),
    (None, PAST),                                   # our own record says it expired: no lookup
])
def test_expired_or_unreadable_open_session_starts_a_fresh_one(monkeypatch, priced, retrieved, expires):
    calls = _stripe(monkeypatch, retrieve=retrieved)
    org = _org(live_tracker_open_session_id="cs_old", live_tracker_open_session_expires_at=expires)
    out, db = _checkout(org)
    assert calls["create"] == 1 and out["checkout_url"] == "https://checkout.stripe.test/new"
    assert db.updates[-1]["live_tracker_open_session_id"] == "cs_test_new_1"
    if expires is PAST:
        assert calls["retrieve"] == []


def test_org_unlocked_between_the_page_load_and_the_lock_gets_409(monkeypatch, priced):
    calls = _stripe(monkeypatch)
    db = _CheckoutDB(_org(**PAID))                 # the locked, fresh row is already paid
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(), org=_org(), db=db))
    assert exc.value.status_code == 409 and calls["create"] == 0


# ── M1: a second paid session is flagged for refund ──────────────────────────
class _GrantDB(_StubDB):
    """Webhook DB where the grant UPDATE matches no row (already unlocked) and the
    org's granting session is `granted_sid`."""
    def __init__(self, granted_sid="cs_test_first", extra_exists=False):
        super().__init__()
        self.granted_sid = granted_sid
        self.extra_exists = extra_exists
        self.selects = 0

    async def execute(self, stmt=None, *_a, **_k):
        self.executed += 1
        if stmt.__class__.__name__ == "Update":
            return SimpleNamespace(rowcount=0)
        self.selects += 1
        if self.selects == 1:
            row = None if self.granted_sid is None else (self.granted_sid,)
        else:
            row = ("cs_test_second",) if self.extra_exists else None
        return SimpleNamespace(first=lambda: row)


def _extras(db):
    return [a for a in db.added if isinstance(a, LiveTrackerExtraPayment)]


def test_second_paid_session_is_recorded_for_refund_and_logged(caplog):
    obj = _live_tracker_session(org_id="00000000-0000-0000-0000-0000000000aa", sid="cs_test_second")
    obj.update(payment_intent="pi_test_2", amount_total=700, currency="usd")
    db = _GrantDB()
    body = _event("checkout.session.completed", obj, event_id="evt_second")
    with caplog.at_level(logging.WARNING, logger="backend.services.live_tracker"):
        out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True} and db.committed
    [extra] = _extras(db)
    assert extra.checkout_session_id == "cs_test_second" and extra.needs_refund is True
    assert extra.payment_intent_id == "pi_test_2" and extra.amount_total == 700 and extra.currency == "usd"
    assert any("extra paid checkout session cs_test_second" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("granted_sid,extra_exists", [
    ("cs_test_second", False),     # a second event for the SAME session that granted
    (None, False),                 # unknown org
    ("cs_test_first", True),       # already flagged (a distinct event for the same session)
])
def test_no_refund_flag_when_it_is_not_a_second_payment(granted_sid, extra_exists):
    obj = _live_tracker_session(org_id="00000000-0000-0000-0000-0000000000aa", sid="cs_test_second")
    db = _GrantDB(granted_sid=granted_sid, extra_exists=extra_exists)
    body = _event("checkout.session.async_payment_succeeded", obj, event_id="evt_x")
    _call(body, _sign(body, int(time.time())), db)
    assert _extras(db) == []


def test_first_grant_records_no_refund():
    db = _StubDB()        # its UPDATE result reports rowcount=1: the grant happened
    body = _event("checkout.session.completed", _live_tracker_session(), event_id="evt_first")
    _call(body, _sign(body, int(time.time())), db)
    assert _extras(db) == [] and db.executed == 1


def test_grant_clears_the_remembered_open_session():
    captured = []

    class _DB:
        async def execute(self, stmt, *a, **k):
            captured.append(stmt.compile().params)
            return SimpleNamespace(rowcount=1)

    asyncio.run(lt.grant_live_tracker(_DB(), "o1", "cs_test_1"))
    assert captured[0]["live_tracker_open_session_id"] is None
    assert captured[0]["live_tracker_open_session_expires_at"] is None


# ── H1: POST /reports cannot be a side door around the $7 paywall ─────────────
class _NoDB:
    def __getattr__(self, name):
        raise AssertionError(f"db.{name} must not be touched for a refused request")


def test_reports_route_refuses_live_game_for_an_unpaid_org():
    body = reports_router.ReportCreate(title="Halftime", sport="football",
                                       game_ids=["11111111-1111-1111-1111-111111111111"],
                                       report_type="live_game")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(reports_router.create_report(body, user=_user(), org=_org(), db=_NoDB()))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "live_tracker_payment_required"
    assert exc.value.detail["checkout_url"] == "/live-tracker"


def test_reports_retry_refuses_a_live_game_report_for_an_unpaid_org():
    report = SimpleNamespace(id="r1", organization_id="o1", generated_at=None, error_reason="boom",
                             report_type="live_game")

    class _DB:
        async def execute(self, *_a, **_k):
            return SimpleNamespace(scalar_one_or_none=lambda: report)

        def add(self, _obj):
            raise AssertionError("no job may be queued")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(reports_router.retry_report("r1", user=SimpleNamespace(organization_id="o1"),
                                                org=_org(), db=_DB()))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "live_tracker_payment_required"


# ── L2: test mode only outside production ─────────────────────────────────────
@pytest.mark.parametrize("env,key,refused", [
    ("test", "sk_live_placeholder", True),
    ("staging", "rk_live_placeholder", True),
    ("staging", "sk_test_placeholder", False),
    ("production", "sk_live_placeholder", False),
    ("staging", "", False),
])
def test_live_key_detection(monkeypatch, env, key, refused):
    monkeypatch.setattr(settings, "ENVIRONMENT", env)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", key)
    assert stripe_mode.live_key_outside_production() is refused
    if refused:
        with pytest.raises(RuntimeError) as exc:
            stripe_mode.assert_stripe_mode_safe_at_startup()
        assert "STRIPE_SECRET_KEY" in str(exc.value) and key not in str(exc.value)   # no secret echoed
    else:
        stripe_mode.assert_stripe_mode_safe_at_startup()


def test_app_refuses_to_start_with_a_live_key_outside_production(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_placeholder")
    monkeypatch.setattr(settings, "WORKERS_IN_API", "none")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_every_checkout_refuses_a_live_key_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_placeholder")
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_x")
    calls = _stripe(monkeypatch)
    monkeypatch.setattr(billing.stripe.Customer, "create",
                        lambda **k: (_ for _ in ()).throw(AssertionError("no Stripe call")))

    with pytest.raises(HTTPException) as e1:
        _checkout(_org())
    with pytest.raises(HTTPException) as e2:
        asyncio.run(billing.create_checkout(billing.CheckoutRequest(tier="coach", success_url="https://app.coachlenz.com/s", cancel_url="https://app.coachlenz.com/c"), _req(),
                                            user=_user(), org=_org(), db=_NoDB()))
    with pytest.raises(HTTPException) as e3:
        asyncio.run(credits_router.buy_bundle(SimpleNamespace(bundle="starter"), _req(),
                                              user=_user(), org=_org(), db=_NoDB()))
    for e in (e1, e2, e3):
        assert e.value.status_code == 503 and "test mode" in e.value.detail
    assert calls["create"] == 0


def _livemode_event(livemode, event_id="evt_lm"):
    import json
    body = json.loads(_event("checkout.session.completed", _live_tracker_session(), event_id=event_id))
    body["livemode"] = livemode
    return json.dumps(body)


@pytest.mark.parametrize("env,livemode", [("test", True), ("staging", True), ("production", False)])
def test_webhook_ignores_events_from_the_other_mode(monkeypatch, env, livemode):
    monkeypatch.setattr(settings, "ENVIRONMENT", env)
    db = _StubDB()
    body = _livemode_event(livemode)
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True, "ignored": "livemode_mismatch"}
    # Not recorded as processed, no grant, nothing committed.
    assert db.added == [] and db.executed == 0 and not db.committed


@pytest.mark.parametrize("env,livemode", [("staging", False), ("production", True)])
def test_webhook_processes_events_from_its_own_mode(monkeypatch, env, livemode):
    monkeypatch.setattr(settings, "ENVIRONMENT", env)
    db = _StubDB()
    body = _livemode_event(livemode)
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True}
    assert db.added[0].event_id == "evt_lm" and db.executed == 1 and db.committed


def test_livemode_check_runs_after_the_signature_check(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    body = _livemode_event(True)
    with pytest.raises(HTTPException) as exc:
        _call(body, _sign(body, int(time.time()), secret="whsec_wrong"))
    assert exc.value.status_code == 400
