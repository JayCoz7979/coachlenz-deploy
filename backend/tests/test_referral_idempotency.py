"""Finding #1: referral commission payout must be idempotent so a worker crash /
retry can never credit the referrer twice (real money out)."""
import asyncio

import pytest

import backend.workers.worker_referrals as wr


def test_idempotency_key_is_deterministic_per_referral_and_invoice():
    k1 = wr._referral_idempotency_key("ref-abc", "in_123")
    k2 = wr._referral_idempotency_key("ref-abc", "in_123")
    assert k1 == k2 == "refcredit:ref-abc:in_123"
    # Different invoice -> different key; missing invoice -> stable sentinel.
    assert wr._referral_idempotency_key("ref-abc", "in_999") != k1
    assert wr._referral_idempotency_key("ref-abc", None) == "refcredit:ref-abc:noinvoice"


def test_credit_referrer_passes_idempotency_key(monkeypatch):
    calls = []

    def _capture(customer_id, **kwargs):
        calls.append((customer_id, kwargs))
        return object()

    monkeypatch.setattr(wr.stripe.Customer, "create_balance_transaction", _capture)
    asyncio.run(wr._credit_referrer("cus_1", 500, 10.0, referral_id="ref-1", invoice_id="in_1"))

    assert len(calls) == 1
    customer_id, kwargs = calls[0]
    assert customer_id == "cus_1"
    assert kwargs["amount"] == -500              # credit (negative balance txn)
    assert kwargs["currency"] == "usd"
    assert kwargs["idempotency_key"] == "refcredit:ref-1:in_1"


def test_credit_referrer_noop_on_zero(monkeypatch):
    calls = []
    monkeypatch.setattr(wr.stripe.Customer, "create_balance_transaction",
                        lambda *a, **k: calls.append((a, k)))
    asyncio.run(wr._credit_referrer("cus_1", 0, 10.0, referral_id="ref-1", invoice_id="in_1"))
    asyncio.run(wr._credit_referrer("cus_1", -5, 10.0, referral_id="ref-1", invoice_id="in_1"))
    assert calls == []  # nothing charged for a zero/negative commission
