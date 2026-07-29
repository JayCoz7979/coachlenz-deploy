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


class _NoDB:
    """Fails loudly if any accepted path tries to touch the database — these smoke
    payloads are intentionally side-effect-free."""
    async def execute(self, *_a, **_k):
        raise AssertionError("webhook should not hit the DB for this payload")

    async def commit(self):
        raise AssertionError("webhook should not commit for this payload")


def _event(event_type: str, obj: dict) -> str:
    # "object": "event" is present on every real Stripe event envelope; stripe>=15
    # reads it in construct_event to tell v1 from v2.core events.
    return json.dumps({"id": "evt_test", "object": "event", "type": event_type,
                       "data": {"object": obj}})


def _call(body: str, header):
    return asyncio.run(stripe_webhook(
        _FakeRequest(body.encode()), stripe_signature=header, db=_NoDB(),
    ))


def test_correctly_signed_event_is_accepted():
    # No metadata -> handler routes but writes nothing (NoDB guards that).
    body = _event("checkout.session.completed", {"metadata": {}})
    out = _call(body, _sign(body, int(time.time())))
    assert out == {"received": True}


def test_signed_event_without_side_effects_is_routed():
    # invoice.payment_failed with no customer -> harmless, no DB.
    body = _event("invoice.payment_failed", {})
    out = _call(body, _sign(body, int(time.time())))
    assert out == {"received": True}


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
