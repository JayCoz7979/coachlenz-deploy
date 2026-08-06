"""Finding #13: /checkout must not mint a second subscription for an org that
already has a live one (which orphans the first and double-bills)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.routers.billing as billing


class _DB:
    def __init__(self):
        self.added = []

    async def execute(self, *_a, **_k):
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _req():
    # create_checkout reads request.client.host + request.headers.get for the
    # chargeback IP log; a minimal stand-in is enough for these unit paths.
    return SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"),
                           headers={"user-agent": "pytest"})


def _org(**kw):
    base = dict(id="o1", name="Test HS", stripe_customer_id="cus_1",
                stripe_subscription_status=None, stripe_subscription_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _user():
    return SimpleNamespace(id="u1", email="coach@example.com")


def _body():
    return billing.CheckoutRequest(tier="coach", success_url="s", cancel_url="c")


@pytest.mark.parametrize("status", ["active", "trialing", "past_due"])
def test_live_subscription_blocks_second_checkout(monkeypatch, status):
    monkeypatch.setattr(billing, "PRICE_MAP", {"coach": "price_x"})
    stripe_calls = {"n": 0}
    monkeypatch.setattr(billing.stripe.checkout.Session, "create",
                        lambda **k: stripe_calls.__setitem__("n", stripe_calls["n"] + 1))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing.create_checkout(
            _body(), _req(), user=_user(), org=_org(stripe_subscription_status=status), db=_DB()))
    assert exc.value.status_code == 409
    assert stripe_calls["n"] == 0  # bailed before creating a Stripe session


def test_no_active_subscription_proceeds(monkeypatch):
    monkeypatch.setattr(billing, "PRICE_MAP", {"coach": "price_x"})
    monkeypatch.setattr(billing.stripe.checkout.Session, "create",
                        lambda **k: SimpleNamespace(url="https://checkout.example", id="sess_1"))
    out = asyncio.run(billing.create_checkout(
        _body(), _req(), user=_user(), org=_org(stripe_subscription_status=None), db=_DB()))
    assert out["checkout_url"] == "https://checkout.example"


def test_canceled_status_can_resubscribe(monkeypatch):
    monkeypatch.setattr(billing, "PRICE_MAP", {"coach": "price_x"})
    monkeypatch.setattr(billing.stripe.checkout.Session, "create",
                        lambda **k: SimpleNamespace(url="https://checkout.example", id="sess_1"))
    out = asyncio.run(billing.create_checkout(
        _body(), _req(), user=_user(), org=_org(stripe_subscription_status="canceled"), db=_DB()))
    assert out["checkout_url"] == "https://checkout.example"
