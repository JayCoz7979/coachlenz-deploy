"""
Track 1.3 — Stripe webhook smoke tests.

Verifies the billing webhook's signature gate locally, WITHOUT calling live
Stripe: we sign payloads ourselves with the same HMAC-SHA256 scheme Stripe uses
(`t=<ts>,v1=<hexdigest of "<ts>.<body>">`) against the test webhook secret that
conftest injects, then drive the async handler with asyncio.run.

Covers: correctly-signed event accepted; tampered body rejected; missing
signature rejected; stale/replayed timestamp rejected (beyond Stripe's 300s
tolerance). The accepted-event payloads carry no metadata/customer, so the
handler routes them without any DB write — the stub DB raises if touched.
"""
import asyncio
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.routers.billing import stripe_webhook

SECRET = settings.STRIPE_WEBHOOK_SECRET  # conftest sets this to a test placeholder


def _sign(payload: str, ts: int, secret: str = SECRET) -> str:
    signed = f"{ts}.{payload}".encode()
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


class _FakeResult:
    def scalar_one_or_none(self):
        return None

    def scalar_one(self):
        return 0


class _StubDB:
    """Minimal fake session. Records the idempotency marker (add) and effect writes
    (execute), and lets flush() simulate a redelivery via `duplicate=True` (the marker
    insert collides -> IntegrityError)."""
    def __init__(self, duplicate=False):
        self.duplicate = duplicate
        self.added = []
        self.executed = 0
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.duplicate:
            raise IntegrityError("duplicate event", {}, Exception("unique_violation"))

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def execute(self, *_a, **_k):
        self.executed += 1
        return _FakeResult()


def _event(event_type: str, obj: dict, event_id: str = "evt_test") -> str:
    # "object": "event" is present on every real Stripe event envelope; stripe>=15
    # reads it in construct_event to tell v1 from v2.core events.
    return json.dumps({"id": event_id, "object": "event", "type": event_type,
                       "data": {"object": obj}})


def _call(body: str, header, db=None):
    return asyncio.run(stripe_webhook(
        _FakeRequest(body.encode()), stripe_signature=header, db=db or _StubDB(),
    ))


def test_correctly_signed_event_is_accepted():
    # No metadata -> handler records the idempotency marker + commits, no effect write.
    db = _StubDB()
    body = _event("checkout.session.completed", {"metadata": {}})
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True}
    assert len(db.added) == 1 and db.committed        # marker persisted
    assert db.executed == 0                            # no metadata -> no subscription flip


def test_signed_event_without_side_effects_is_routed():
    # invoice.payment_failed with no customer -> marker only, no effect.
    db = _StubDB()
    body = _event("invoice.payment_failed", {})
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True}
    assert db.executed == 0 and db.committed


def test_first_delivery_processes_and_records_marker():
    # A checkout with metadata: the effect runs once AND the event id is recorded.
    from backend.models.billing_event import ProcessedStripeEvent
    db = _StubDB()
    body = _event("checkout.session.completed", {"metadata": {"org_id": "o1", "tier": "coach"}})
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True}
    assert db.executed == 1 and db.committed           # subscription flip ran once
    assert isinstance(db.added[0], ProcessedStripeEvent) and db.added[0].event_id == "evt_test"


def test_redelivered_event_is_skipped_no_double_effect():
    # Stripe redelivers the same event id -> marker insert collides -> skip. The effect
    # (which would grant a second referral credit / re-flip the subscription) must NOT run.
    db = _StubDB(duplicate=True)
    body = _event("invoice.payment_succeeded",
                  {"customer": "cus_1", "subscription": "sub_1", "id": "in_1"})
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True, "duplicate": True}
    assert db.executed == 0            # effect never applied a second time
    assert db.rolled_back and not db.committed


def test_canceled_subscription_does_not_regrant_a_trial():
    # Finding #16: on customer.subscription.deleted the org must NOT be flipped back
    # into an active trial (is_trial=True regranted trial features + a free slot to a
    # churned customer). It should downgrade with is_trial=False.
    captured = []

    class _CapDB(_StubDB):
        async def execute(self, *a, **k):
            if a:
                captured.append(a[0])
            return _FakeResult()

    db = _CapDB()
    body = _event("customer.subscription.deleted", {"id": "sub_1"})
    out = _call(body, _sign(body, int(time.time())), db)
    assert out == {"received": True}
    updates = [s for s in captured if s.__class__.__name__ == "Update"]
    assert updates, "expected an Organization update on cancellation"
    params = updates[-1].compile().params
    assert params.get("is_trial") is False
    assert params.get("stripe_subscription_status") == "canceled"


def test_tampered_payload_is_rejected():
    signed_body = _event("checkout.session.completed", {"metadata": {}})
    header = _sign(signed_body, int(time.time()))
    tampered = _event("checkout.session.completed",
                      {"metadata": {"tier": "elite", "org_id": "attacker"}})
    with pytest.raises(HTTPException) as exc:
        _call(tampered, header)  # signature was for a different body
    assert exc.value.status_code == 400


def test_missing_signature_is_rejected():
    body = _event("checkout.session.completed", {"metadata": {}})
    with pytest.raises(HTTPException) as exc:
        _call(body, None)
    assert exc.value.status_code == 400


def test_stale_replayed_timestamp_is_rejected():
    body = _event("checkout.session.completed", {"metadata": {}})
    stale = int(time.time()) - 10_000  # well beyond Stripe's 300s tolerance
    with pytest.raises(HTTPException) as exc:
        _call(body, _sign(body, stale))
    assert exc.value.status_code == 400
