"""
Unit tests for the entitlement gates (backend/services/entitlements.py): the trial
paid-feature locks and the verify-email + pick-a-sport analysis gate. Pure logic
against lightweight fake org/user objects — no DB, no web stack.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.entitlements import assert_feature_allowed, assert_ready_to_analyze


def _org(is_trial=True, days_left=5, sports=None):
    ends = datetime.utcnow() + timedelta(days=days_left)  # future = active, past = expired
    return SimpleNamespace(is_trial=is_trial, trial_ends_at=ends, chosen_sports=sports or [])


def _user(verified=True):
    return SimpleNamespace(email_verified=verified)


# ── Feature locks ────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("feature", ["advanced_tendencies", "multi_game_reports", "film_packages", "coach_tenure"])
def test_active_trial_blocks_locked_features(feature):
    with pytest.raises(HTTPException) as e:
        assert_feature_allowed(_org(), feature)
    assert e.value.status_code == 403


@pytest.mark.unit
def test_active_trial_allows_unlocked_feature():
    assert_feature_allowed(_org(), "some_free_feature")  # not in TRIAL_LOCKED_FEATURES


@pytest.mark.unit
def test_paid_org_allows_all_features():
    for feature in ("advanced_tendencies", "multi_game_reports", "film_packages"):
        assert_feature_allowed(_org(is_trial=False), feature)  # no raise


@pytest.mark.unit
def test_expired_trial_allows_features():
    # An expired trial is no longer "active", so locks lift (they must pay, but the
    # gate is is_trial_active, not is_trial).
    assert_feature_allowed(_org(days_left=-1), "film_packages")  # no raise


# ── Verify + pick-a-sport analysis gate ──────────────────────────────────────

@pytest.mark.unit
def test_paid_org_ready_regardless():
    # Paid org passes even with no verification and no sport.
    assert_ready_to_analyze(_org(is_trial=False, sports=[]), _user(verified=False))


@pytest.mark.unit
def test_expired_trial_ready():
    assert_ready_to_analyze(_org(days_left=-1, sports=[]), _user(verified=False))


@pytest.mark.unit
def test_active_trial_unverified_blocked():
    with pytest.raises(HTTPException) as e:
        assert_ready_to_analyze(_org(sports=["basketball"]), _user(verified=False))
    assert e.value.status_code == 403
    assert "email" in e.value.detail.lower()


@pytest.mark.unit
def test_active_trial_verified_but_no_sport_blocked():
    with pytest.raises(HTTPException) as e:
        assert_ready_to_analyze(_org(sports=[]), _user(verified=True))
    assert e.value.status_code == 403
    assert "sport" in e.value.detail.lower()


@pytest.mark.unit
def test_active_trial_verified_and_sport_locked_ready():
    assert_ready_to_analyze(_org(sports=["football"]), _user(verified=True))  # no raise
