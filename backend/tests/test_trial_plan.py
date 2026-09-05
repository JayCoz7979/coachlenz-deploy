"""
plan_for (pure): paid | trial | free. 'free' is the permanent Live Game Logger tier
an org lands in after the trial expires without paying. No DB, no framework.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services.trial import plan_for


def _org(**kw):
    base = dict(is_trial=True, trial_ends_at=None, stripe_subscription_status=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_active_subscription_is_paid():
    for status in ("active", "trialing", "past_due"):
        assert plan_for(_org(stripe_subscription_status=status)) == "paid"


def test_paid_wins_even_if_trial_flags_linger():
    # A converted trial can keep is_trial True; an active sub still reads as paid.
    assert plan_for(_org(stripe_subscription_status="active",
                         trial_ends_at=datetime.utcnow() + timedelta(days=3))) == "paid"


def test_in_window_trial_is_trial():
    assert plan_for(_org(trial_ends_at=datetime.utcnow() + timedelta(days=5))) == "trial"


def test_non_expiring_trial_is_trial():
    assert plan_for(_org(trial_ends_at=None)) == "trial"


def test_expired_trial_is_free_not_locked_out():
    assert plan_for(_org(trial_ends_at=datetime.utcnow() - timedelta(days=1))) == "free"


def test_non_trial_no_subscription_is_free():
    assert plan_for(_org(is_trial=False)) == "free"


def test_canceled_subscription_is_free():
    assert plan_for(_org(is_trial=False, stripe_subscription_status="canceled")) == "free"
