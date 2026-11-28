"""
$7 Live Tracker (Live Game Logger + Halftime Sheet): checkout, webhook grant, and the
server-side /live gate. No DB, no network, no live Stripe.

Product decision (Nov 28): everyone pays $7, including current users. No
grandfathering, so an EXISTING unpaid org is blocked exactly like a new one.

Covers:
  * the /live gate over real HTTP (slim app, real router, dependency overrides):
    an existing unpaid user cannot start, log, edit, delete, flag, or report and gets
    the paywall payload; their past games stay readable. A paid user has full access.
  * checkout: fails closed when STRIPE_PRICE_LIVE_TRACKER is unset; one-time payment
    with the env price id, quantity 1, kind=live_tracker metadata; never inline price_data.
  * webhook: valid signature grants once; bad signature 400; redelivery is a no-op;
    unpaid / failed / expired sessions grant nothing; async success grants.
"""
import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.routers import billing, live_game
from backend.services import live_tracker as lt
from backend.services.auth import get_current_user, get_current_org
from backend.models.base import get_db

pytestmark = pytest.mark.unit

ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
GAME_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


def _org(paid: bool):
    # An EXISTING account: created long ago, on a paid subscription plan, has logged
    # games before. Only the $7 purchase decides access.
    return SimpleNamespace(
        id=ORG_ID, name="Tanner HS", is_trial=False, trial_ends_at=None,
        subscription_tier="coach", stripe_subscription_status="active",
        chosen_sports=["football"], stripe_customer_id="cus_existing",
        live_tracker_purchased_at=datetime(2026, 11, 28, tzinfo=timezone.utc) if paid else None,
        live_tracker_checkout_session_id="cs_test_paid" if paid else None,
        admin_level=None,
    )


def _user():
    return SimpleNamespace(id=USER_ID, organization_id=ORG_ID, email="coach@example.com",
                           name="Coach", email_verified=True, role="owner")


# ── unit: the entitlement helpers ────────────────────────────────────────────
def test_no_grandfathering_existing_org_without_purchase_has_no_access():
    assert lt.has_live_tracker_access(_org(paid=False)) is False
    assert lt.has_live_tracker_access(None) is False
    assert lt.has_live_tracker_access(_org(paid=True)) is True


def test_paywall_detail_is_honest_and_points_at_checkout():
    d = lt.paywall_detail()
    assert d["code"] == "live_tracker_payment_required"
    assert d["checkout_path"] == "/live-tracker"
    assert d["price_usd"] == 7
    assert "$7 one-time" in d["message"]
    assert "past games and reports stay viewable" in d["message"]
    low = d["message"].lower()
    assert "free forever" not in low and "sms" not in low


def test_assert_access_raises_402_for_unpaid():
    with pytest.raises(HTTPException) as exc:
        lt.assert_live_tracker_access(_org(paid=False))
    assert exc.value.status_code == 402
    assert exc.value.detail["code"] == "live_tracker_payment_required"
    lt.assert_live_tracker_access(_org(paid=True))  # no raise


def test_only_a_paid_session_counts():
    assert lt.checkout_session_is_paid({"payment_status": "paid"}) is True
    for status in ("unpaid", "no_payment_required", None):
        assert lt.checkout_session_is_paid({"payment_status": status}) is False


# ── HTTP: the /live gate ─────────────────────────────────────────────────────
class _Result:
    def __init__(self, one=None, many=None):
        self._one, self._many = one, many or []

    def scalar_one_or_none(self):
        return self._one

    def scalar_one(self):
        return self._one if self._one is not None else 0

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._many))


class _LiveDB:
    """Just enough session for the live routes. Games query -> the one live game;
    events queries -> no rows. Counts writes so a refused request can be proven
    to have written nothing."""
    def __init__(self):
        self.added, self.commits = [], 0
        self.game = SimpleNamespace(id=GAME_ID, organization_id=ORG_ID, sport="football",
                                    opponent="Rivals", status="live", team_id=None,
                                    game_date=None, created_at=None)

    async def execute(self, stmt, *_a, **_k):
        text = str(stmt)
        if "FROM games" in text:
            return _Result(one=self.game, many=[self.game])
        return _Result()

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    def add_all(self, objs):
        for o in objs:
            self.add(o)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        self.added.append(("deleted", obj))


def _client(paid: bool, monkeypatch):
    app = FastAPI()
    app.include_router(live_game.router)
    db = _LiveDB()
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_current_org] = lambda: _org(paid)

    async def _db():
        yield db
    app.dependency_overrides[get_db] = _db

    async def _no_log(**_k):
        return None

    async def _consented(_db, _org_id):
        return None
    monkeypatch.setattr(live_game, "log_agent_action", _no_log)
    monkeypatch.setattr(live_game, "assert_student_consent", _consented)
    return TestClient(app), db


SESSION_BODY = {"sport": "football", "team_name": "Tanner", "opponent": "Athens"}

# Every /live WRITE route, with a valid body. Each must refuse an unpaid org.
WRITE_CALLS = [
    ("post", "/live/session", SESSION_BODY),
    ("post", "/live/plays", {"session_id": str(GAME_ID), "plays": [{"possession": "us", "play_type": "Run"}]}),
    ("patch", f"/live/play/{uuid.uuid4()}", {"yards_gained": 4}),
    ("delete", f"/live/play/{uuid.uuid4()}", None),
    ("post", f"/live/play/{uuid.uuid4()}/flag", {"is_coaching_point": True}),
    ("post", "/live/report", {"session_id": str(GAME_ID), "scope": "halftime", "period": 2}),
]


def _call(client, method, path, body):
    fn = getattr(client, method)
    return fn(path, json=body) if body is not None else fn(path)


@pytest.mark.parametrize("method,path,body", WRITE_CALLS)
def test_existing_unpaid_user_is_blocked_on_every_live_write_route(method, path, body, monkeypatch):
    client, db = _client(paid=False, monkeypatch=monkeypatch)
    r = _call(client, method, path, body)
    assert r.status_code == 402, (path, r.text)
    detail = r.json()["detail"]
    assert detail["code"] == "live_tracker_payment_required"
    assert detail["checkout_path"] == "/live-tracker"
    assert db.added == [] and db.commits == 0      # refused before any write


def test_existing_unpaid_user_cannot_start_a_new_game_and_sees_paywall(monkeypatch):
    client, db = _client(paid=False, monkeypatch=monkeypatch)
    r = client.post("/live/session", json=SESSION_BODY)
    assert r.status_code == 402
    assert "$7 one-time" in r.json()["detail"]["message"]
    access = client.get("/live/access").json()
    assert access["live_tracker"] is False
    assert access["checkout_path"] == "/live-tracker"
    assert access["code"] == "live_tracker_payment_required"


def test_existing_unpaid_user_past_games_stay_viewable(monkeypatch):
    client, _db = _client(paid=False, monkeypatch=monkeypatch)
    listing = client.get("/live/sessions")
    assert listing.status_code == 200
    assert listing.json()["sessions"][0]["session_id"] == str(GAME_ID)
    assert listing.json()["access"]["live_tracker"] is False
    one = client.get(f"/live/session/{GAME_ID}")
    assert one.status_code == 200
    assert one.json()["access"]["live_tracker"] is False


def test_paid_user_has_full_access(monkeypatch):
    client, db = _client(paid=True, monkeypatch=monkeypatch)
    assert client.get("/live/access").json()["live_tracker"] is True

    start = client.post("/live/session", json=SESSION_BODY)
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "live"

    logged = client.post("/live/plays", json={"session_id": str(GAME_ID), "plays": [
        {"possession": "us", "play_type": "Run", "yards_gained": 5, "client_uid": "u1"}]})
    assert logged.status_code == 200, logged.text
    assert logged.json()["plays_written"] == 1

    got = client.get(f"/live/session/{GAME_ID}")
    assert got.status_code == 200 and got.json()["access"]["live_tracker"] is True


def test_paid_user_report_reaches_the_play_count_rule_not_the_paywall(monkeypatch):
    # 0 plays -> the existing 422 thin-log rule (no row, no job), proving the paid
    # request passed the gate and the #296 rules still apply.
    client, db = _client(paid=True, monkeypatch=monkeypatch)
    r = client.post("/live/report", json={"session_id": str(GAME_ID), "scope": "halftime"})
    assert r.status_code == 422
    assert db.added == []


# ── checkout ─────────────────────────────────────────────────────────────────
class _Req:
    client = SimpleNamespace(host="203.0.113.7")
    headers = {"user-agent": "pytest"}


class _CheckoutDB:
    def __init__(self):
        self.added = []

    def add(self, o):
        self.added.append(o)

    async def execute(self, *_a, **_k):
        return None

    async def commit(self):
        pass


def _checkout(org, origin=None):
    return asyncio.run(billing.create_live_tracker_checkout(
        body=billing.LiveTrackerCheckoutRequest(origin=origin), request=_Req(),
        user=_user(), org=org, db=_CheckoutDB()))


def test_checkout_fails_closed_without_price_env(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "")
    called = []
    monkeypatch.setattr(billing.stripe.checkout.Session, "create", lambda **k: called.append(k))
    with pytest.raises(HTTPException) as exc:
        _checkout(_org(paid=False))
    assert exc.value.status_code == 503
    assert called == []                          # Stripe never called


def test_checkout_fails_closed_without_stripe_key(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    with pytest.raises(HTTPException) as exc:
        _checkout(_org(paid=False))
    assert exc.value.status_code == 503


def test_checkout_is_one_time_payment_with_env_price(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(settings, "APP_URL", "https://app.coachlenz.com")
    seen = {}

    def _create(**kw):
        seen.update(kw)
        return SimpleNamespace(url="https://checkout.stripe.test/c/1", id="cs_test_1")
    monkeypatch.setattr(billing.stripe.checkout.Session, "create", _create)

    out = _checkout(_org(paid=False), origin="https://evil.example")
    assert out == {"checkout_url": "https://checkout.stripe.test/c/1"}
    assert seen["mode"] == "payment"
    assert seen["line_items"] == [{"price": "price_test_live", "quantity": 1}]
    assert "price_data" not in json.dumps(seen["line_items"])   # never an inline $7
    assert seen["metadata"]["kind"] == "live_tracker"
    assert seen["metadata"]["org_id"] == str(ORG_ID)
    # An untrusted origin falls back to APP_URL; paths are fixed server-side.
    assert seen["success_url"] == "https://app.coachlenz.com/live-tracker/success?session_id={CHECKOUT_SESSION_ID}"
    assert seen["cancel_url"] == "https://app.coachlenz.com/live-tracker?checkout=cancelled"


def test_checkout_uses_an_allowed_origin(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_placeholder")
    seen = {}
    monkeypatch.setattr(billing.stripe.checkout.Session, "create",
                        lambda **kw: seen.update(kw) or SimpleNamespace(url="u", id="cs"))
    _checkout(_org(paid=False), origin="https://app.coachlenz.com")
    assert seen["cancel_url"].startswith("https://app.coachlenz.com/live-tracker")


def test_checkout_refuses_an_org_that_already_paid(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(billing.stripe.checkout.Session, "create",
                        lambda **kw: pytest.fail("must not open a second checkout"))
    with pytest.raises(HTTPException) as exc:
        _checkout(_org(paid=True))
    assert exc.value.status_code == 409


# ── webhook ──────────────────────────────────────────────────────────────────
SECRET = settings.STRIPE_WEBHOOK_SECRET


def _sign(payload: str, secret: str = SECRET) -> str:
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _event(event_type, obj, event_id="evt_lt_1"):
    return json.dumps({"id": event_id, "object": "event", "type": event_type,
                       "data": {"object": obj}})


class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self):
        return self._body


class _WebhookDB:
    """Captures Organization updates; `duplicate=True` simulates a redelivered event
    (the ProcessedStripeEvent marker insert collides)."""
    def __init__(self, duplicate=False):
        self.duplicate = duplicate
        self.added, self.updates = [], []
        self.committed = self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.duplicate:
            raise IntegrityError("dup", {}, Exception("unique_violation"))

    async def execute(self, stmt, *_a, **_k):
        if stmt.__class__.__name__ == "Update":
            self.updates.append(stmt.compile().params)
        return SimpleNamespace(scalar_one_or_none=lambda: None, scalar_one=lambda: 0)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _hook(body: str, header, db):
    return asyncio.run(billing.stripe_webhook(_FakeRequest(body.encode()), stripe_signature=header, db=db))


def _session(payment_status="paid", kind="live_tracker"):
    return {"id": "cs_test_lt", "object": "checkout.session", "mode": "payment",
            "payment_status": payment_status, "customer": "cus_existing",
            "metadata": {"org_id": str(ORG_ID), "kind": kind}}


def _grants(db):
    return [u for u in db.updates if "live_tracker_purchased_at" in u]


def test_valid_signed_paid_checkout_grants_access_once():
    db = _WebhookDB()
    body = _event("checkout.session.completed", _session("paid"))
    assert _hook(body, _sign(body), db) == {"received": True}
    grants = _grants(db)
    assert len(grants) == 1
    assert grants[0]["live_tracker_checkout_session_id"] == "cs_test_lt"
    assert db.committed


def test_grant_is_guarded_to_the_first_purchase():
    # The UPDATE only matches an org whose purchase timestamp is still NULL, so two
    # different events for the same purchase can never move or re-grant it.
    db = _WebhookDB()
    asyncio.run(lt.grant_live_tracker(db, str(ORG_ID), "cs_1"))

    class _Cap(_WebhookDB):
        async def execute(self, stmt, *_a, **_k):
            self.sql = str(stmt)
            return None
    cap = _Cap()
    asyncio.run(lt.grant_live_tracker(cap, str(ORG_ID), "cs_1"))
    assert "live_tracker_purchased_at IS NULL" in cap.sql


def test_bad_signature_is_rejected_400_and_grants_nothing():
    db = _WebhookDB()
    body = _event("checkout.session.completed", _session("paid"))
    with pytest.raises(HTTPException) as exc:
        _hook(body, _sign(body, secret="whsec_wrong"), db)
    assert exc.value.status_code == 400
    assert _grants(db) == [] and db.added == []


def test_redelivered_event_is_a_noop():
    db = _WebhookDB(duplicate=True)
    body = _event("checkout.session.completed", _session("paid"))
    assert _hook(body, _sign(body), db) == {"received": True, "duplicate": True}
    assert _grants(db) == []
    assert db.rolled_back and not db.committed


@pytest.mark.parametrize("event_type,payment_status", [
    ("checkout.session.completed", "unpaid"),          # delayed method, not yet paid
    ("checkout.session.async_payment_failed", "unpaid"),
    ("checkout.session.expired", "unpaid"),            # coach cancelled / abandoned
])
def test_cancel_or_failed_payment_grants_nothing(event_type, payment_status):
    db = _WebhookDB()
    body = _event(event_type, _session(payment_status))
    assert _hook(body, _sign(body), db) == {"received": True}
    assert _grants(db) == []


def test_async_payment_success_grants():
    db = _WebhookDB()
    body = _event("checkout.session.async_payment_succeeded", _session("paid"))
    _hook(body, _sign(body), db)
    assert len(_grants(db)) == 1


def test_credit_bundle_checkout_does_not_grant_the_live_tracker():
    db = _WebhookDB()
    s = _session("paid", kind="credit_bundle")
    s["metadata"]["credits"] = "0"
    body = _event("checkout.session.completed", s)
    _hook(body, _sign(body), db)
    assert _grants(db) == []
