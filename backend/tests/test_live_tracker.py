"""
$7 one-time Live Tracker unlock: entitlement rules, the server-side /live gate, and
the one-time Checkout endpoint. No DB, no network, no live Stripe: Stripe calls are
monkeypatched and the DB is a stub.

The webhook grant path (signature, idempotency, paid-only) is in
test_stripe_webhook.py; the real-Postgres end-to-end path is in
test_live_game_report_type_pg.py.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import backend.routers.billing as billing
import backend.routers.live_game as live_game
from backend.config import settings
from backend.models.base import get_db
from backend.services import live_tracker as lt
from backend.services.auth import get_current_org, get_current_user

pytestmark = pytest.mark.unit

APP_ORIGIN = "https://app.coachlenz.com"


def _org(**kw):
    base = dict(id="00000000-0000-0000-0000-0000000000aa", name="Test HS",
                stripe_customer_id="cus_1", stripe_subscription_status=None,
                live_tracker_purchased_at=None, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                chosen_sports=["football"], is_trial=False)
    base.update(kw)
    return SimpleNamespace(**base)


PAID = dict(live_tracker_purchased_at=datetime(2026, 11, 28, tzinfo=timezone.utc))


# ── entitlement rules ────────────────────────────────────────────────────────
def test_unpaid_org_has_no_access():
    assert lt.has_live_tracker_access(_org()) is False
    assert lt.access_reason(_org()) is None


def test_purchased_org_has_access():
    assert lt.has_live_tracker_access(_org(**PAID)) is True
    assert lt.access_reason(_org(**PAID)) == "purchased"


def test_active_subscription_has_access():
    assert lt.has_live_tracker_access(_org(stripe_subscription_status="active")) is True


@pytest.mark.parametrize("status", ["trialing", "past_due", "canceled", "incomplete", ""])
def test_non_active_subscription_states_do_not_unlock(status):
    assert lt.has_live_tracker_access(_org(stripe_subscription_status=status)) is False


def test_trial_org_is_not_unlocked_by_being_a_trial():
    assert lt.has_live_tracker_access(_org(is_trial=True)) is False


def test_none_org_is_locked():
    assert lt.has_live_tracker_access(None) is False


def test_grandfather_flag_defaults_off():
    # The shipped default must grandfather NOBODY, however old the org is.
    assert settings.LIVE_TRACKER_GRANDFATHER_BEFORE == ""
    old = _org(created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert lt.has_live_tracker_access(old) is False


def test_grandfather_flag_when_set_only_covers_older_orgs(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRACKER_GRANDFATHER_BEFORE", "2026-12-01")
    assert lt.has_live_tracker_access(_org(created_at=datetime(2026, 11, 30, tzinfo=timezone.utc)))
    assert lt.access_reason(_org(created_at=datetime(2026, 11, 30, tzinfo=timezone.utc))) == "grandfathered"
    assert not lt.has_live_tracker_access(_org(created_at=datetime(2026, 12, 1, tzinfo=timezone.utc)))
    assert not lt.has_live_tracker_access(_org(created_at=None))


def test_malformed_grandfather_value_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRACKER_GRANDFATHER_BEFORE", "yes")
    assert lt.has_live_tracker_access(_org(created_at=datetime(2001, 1, 1, tzinfo=timezone.utc))) is False


def test_assert_access_raises_403_with_paywall_header():
    with pytest.raises(HTTPException) as exc:
        lt.assert_live_tracker_access(_org())
    assert exc.value.status_code == 403
    assert "$7 one-time" in exc.value.detail
    assert exc.value.headers == {"X-CoachLenz-Locked": "live_tracker"}


@pytest.mark.parametrize("obj,expected", [
    ({"mode": "payment", "payment_status": "paid", "metadata": {"kind": "live_tracker", "org_id": "o1"}}, True),
    ({"mode": "payment", "payment_status": "unpaid", "metadata": {"kind": "live_tracker", "org_id": "o1"}}, False),
    ({"mode": "payment", "payment_status": "no_payment_required", "metadata": {"kind": "live_tracker", "org_id": "o1"}}, False),
    ({"mode": "subscription", "payment_status": "paid", "metadata": {"kind": "live_tracker", "org_id": "o1"}}, False),
    ({"mode": "payment", "payment_status": "paid", "metadata": {"kind": "credit_bundle", "org_id": "o1"}}, False),
    ({"mode": "payment", "payment_status": "paid", "metadata": {"kind": "live_tracker"}}, False),
    ({"mode": "payment", "payment_status": "paid"}, False),
])
def test_only_a_paid_live_tracker_payment_session_counts(obj, expected):
    assert lt.live_tracker_session_is_paid(obj) is expected


def test_grant_is_conditional_on_not_already_granted():
    captured = []

    class _DB:
        async def execute(self, stmt, *a, **k):
            captured.append(stmt)

    asyncio.run(lt.grant_live_tracker(_DB(), "o1", "cs_test_1"))
    assert len(captured) == 1
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": False}))
    assert "UPDATE organizations" in sql
    assert "live_tracker_purchased_at IS NULL" in sql      # never re-grants / moves the grant
    params = captured[0].compile().params
    assert params["live_tracker_checkout_session_id"] == "cs_test_1"
    assert params["live_tracker_purchased_at"] is not None


# ── server-side /live gate (HTTP, slim app, dependencies overridden) ─────────
class _Result:
    def scalar_one_or_none(self):
        return None

    def scalar_one(self):
        return 0

    def scalars(self):
        return SimpleNamespace(all=lambda: [])


class _StubDB:
    async def execute(self, *_a, **_k):
        return _Result()

    def add(self, *_a, **_k):
        pass

    def add_all(self, *_a, **_k):
        pass

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, *_a, **_k):
        pass

    async def delete(self, *_a, **_k):
        pass


def _client(org):
    app = FastAPI()
    app.include_router(live_game.router)
    user = SimpleNamespace(id="u1", organization_id=org.id, name="Coach", email="c@example.com",
                           email_verified=True, role="owner")

    async def _db():
        yield _StubDB()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_org] = lambda: org
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


SID = "00000000-0000-0000-0000-0000000000bb"
GATED = [
    ("post", "/live/session", {"sport": "football", "team_name": "Us", "opponent": "Them"}),
    ("get", f"/live/session/{SID}", None),
    ("post", "/live/plays", {"session_id": SID, "plays": [{"possession": "us"}]}),
    ("patch", f"/live/play/{SID}", {"yards_gained": 3}),
    ("delete", f"/live/play/{SID}", None),
    ("post", f"/live/play/{SID}/flag", {"is_coaching_point": True}),
    ("post", "/live/report", {"session_id": SID, "scope": "halftime"}),
]


@pytest.mark.parametrize("method,path,body", GATED)
def test_unpaid_org_is_refused_on_every_logger_route(method, path, body):
    c = _client(_org())
    r = c.request(method.upper(), path, json=body)
    assert r.status_code == 403, r.text
    assert "$7 one-time" in r.json()["detail"]
    assert r.headers.get("x-coachlenz-locked") == "live_tracker"


@pytest.mark.parametrize("method,path,body", [g for g in GATED if g[1] != "/live/session"])
def test_paid_org_passes_the_gate(method, path, body):
    # The stub DB finds nothing, so a request that got PAST the gate is a 404
    # (session / play not found), never the paywall 403.
    c = _client(_org(**PAID))
    r = c.request(method.upper(), path, json=body)
    assert r.status_code == 404, r.text
    assert r.headers.get("x-coachlenz-locked") is None


def test_paid_org_session_create_reaches_the_consent_gate():
    # Paid -> past the Live Tracker gate; the stub DB has no consent row, so the
    # existing student-data consent gate (unchanged) is what answers now.
    c = _client(_org(**PAID))
    r = c.post("/live/session", json={"sport": "football", "team_name": "Us", "opponent": "Them"})
    assert r.headers.get("x-coachlenz-locked") is None
    assert r.status_code == 403
    assert "$7" not in r.json()["detail"]


def test_paid_org_sport_lock_still_applies():
    c = _client(_org(**PAID, chosen_sports=["basketball"]))
    r = c.post("/live/session", json={"sport": "football", "team_name": "Us", "opponent": "Them"})
    assert r.status_code == 403
    assert r.headers.get("x-coachlenz-locked") is None


def test_access_endpoint_reports_state_without_gating(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "")
    r = _client(_org()).get("/live/access")
    assert r.status_code == 200
    assert r.json()["has_access"] is False
    assert r.json()["checkout_available"] is False
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_x")
    r = _client(_org(**PAID)).get("/live/access")
    assert r.json()["has_access"] is True and r.json()["reason"] == "purchased"
    assert r.json()["checkout_available"] is True


def test_every_mutating_or_resume_route_depends_on_the_gate():
    """Guard against a future route slipping past the paywall: every /live route
    except the read-only access probe and the session list must depend on it."""
    open_routes = {("GET", "/live/access"), ("GET", "/live/sessions")}

    def deps(dependant):
        for d in dependant.dependencies:
            yield d.call
            yield from deps(d)

    for route in live_game.router.routes:
        for m in route.methods:
            if (m, route.path) in open_routes:
                continue
            assert live_game.live_tracker_org in set(deps(route.dependant)), (m, route.path)


# ── one-time Checkout ────────────────────────────────────────────────────────
class _CheckoutDB:
    def __init__(self):
        self.added = []

    async def execute(self, *_a, **_k):
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _req():
    return SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={"user-agent": "pytest"})


def _user():
    return SimpleNamespace(id="u1", email="coach@example.com")


def _body(success=f"{APP_ORIGIN}/live-tracker/success", cancel=f"{APP_ORIGIN}/live-tracker?checkout=cancelled"):
    return billing.LiveTrackerCheckoutRequest(success_url=success, cancel_url=cancel)


def _no_stripe(monkeypatch):
    calls = {"n": 0}

    def boom(**_k):
        calls["n"] += 1
        raise AssertionError("Stripe must not be called")

    monkeypatch.setattr(billing.stripe.checkout.Session, "create", boom)
    return calls


@pytest.mark.parametrize("price", ["", "   "])
def test_checkout_fails_closed_when_price_env_unset(monkeypatch, price):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", price)
    calls = _no_stripe(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(), org=_org(), db=_CheckoutDB()))
    assert exc.value.status_code == 503
    assert "isn't available" in exc.value.detail and "Nothing was charged" in exc.value.detail
    assert calls["n"] == 0


def test_checkout_fails_closed_when_secret_key_unset(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_x")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    calls = _no_stripe(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(), org=_org(), db=_CheckoutDB()))
    assert exc.value.status_code == 503
    assert calls["n"] == 0


def test_checkout_creates_one_time_payment_from_env_price(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live_tracker")
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(url="https://checkout.stripe.test/c/pay/cs_test_1", id="cs_test_1")

    monkeypatch.setattr(billing.stripe.checkout.Session, "create", create)
    db = _CheckoutDB()
    out = asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(), org=_org(), db=db))
    assert out == {"checkout_url": "https://checkout.stripe.test/c/pay/cs_test_1"}
    assert seen["mode"] == "payment"
    assert seen["line_items"] == [{"price": "price_test_live_tracker", "quantity": 1}]
    assert "price_data" not in str(seen["line_items"])          # never inlines the amount
    assert seen["metadata"]["kind"] == "live_tracker"
    assert seen["metadata"]["org_id"] == _org().id
    assert seen["client_reference_id"] == _org().id
    assert seen["payment_intent_data"]["metadata"]["kind"] == "live_tracker"
    assert seen["success_url"].startswith(APP_ORIGIN) and seen["cancel_url"].startswith(APP_ORIGIN)
    # Chargeback evidence row, same as the subscription checkout.
    assert db.added and db.added[0].tier == "live_tracker" and db.added[0].stripe_session_id == "cs_test_1"


def test_checkout_creates_customer_when_missing(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live_tracker")
    monkeypatch.setattr(billing.stripe.Customer, "create", lambda **k: SimpleNamespace(id="cus_new"))
    seen = {}
    monkeypatch.setattr(billing.stripe.checkout.Session, "create",
                        lambda **kw: seen.update(kw) or SimpleNamespace(url="u", id="cs_1"))
    asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(),
                                              org=_org(stripe_customer_id=None), db=_CheckoutDB()))
    assert seen["customer"] == "cus_new"


def test_checkout_refuses_an_already_unlocked_org(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_x")
    calls = _no_stripe(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing.live_tracker_checkout(_body(), _req(), user=_user(), org=_org(**PAID), db=_CheckoutDB()))
    assert exc.value.status_code == 409
    assert calls["n"] == 0


@pytest.mark.parametrize("success,cancel", [
    ("https://evil.example/live", f"{APP_ORIGIN}/live-tracker"),
    (f"{APP_ORIGIN}/live-tracker/success", "https://evil.example/x"),
    ("javascript:alert(1)", f"{APP_ORIGIN}/live-tracker"),
    ("/live-tracker/success", f"{APP_ORIGIN}/live-tracker"),
])
def test_checkout_rejects_foreign_return_urls(monkeypatch, success, cancel):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_x")
    calls = _no_stripe(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing.live_tracker_checkout(_body(success, cancel), _req(), user=_user(),
                                                  org=_org(), db=_CheckoutDB()))
    assert exc.value.status_code == 400
    assert calls["n"] == 0
