"""
Guard for bug I-1: every billing tier must have an EXPLICIT sport-limit entry.

The bug (fixed 2026-07-29): billing.PRICE_MAP used tier names
(coach / athletic_dept / district) that were absent from
sports.TIER_SPORT_LIMITS, so a paying org silently fell through to
DEFAULT_SPORT_LIMIT (1) and was capped at ONE sport at onboarding — despite
every paid plan advertising "All sports". These tests fail loudly if the two
maps ever drift apart again.

Pure logic: importing billing.PRICE_MAP only reads env-backed price IDs at
module load (conftest provides placeholder env); no DB or network.
"""
import pytest

from backend.routers.billing import PRICE_MAP
from backend.services.sports import (
    TIER_SPORT_LIMITS, CHOOSABLE_SPORTS, max_sports_for_tier,
)


@pytest.mark.unit
def test_every_billing_tier_has_explicit_sport_limit():
    missing = [t for t in PRICE_MAP if t not in TIER_SPORT_LIMITS]
    assert not missing, (
        "billing tiers missing from TIER_SPORT_LIMITS (would silently default "
        f"to {min(TIER_SPORT_LIMITS.values())} sport and cap paying orgs): {missing}"
    )


@pytest.mark.unit
def test_trial_is_explicit_and_single_sport():
    assert "trial" in TIER_SPORT_LIMITS, "trial must be explicit, not defaulted"
    assert TIER_SPORT_LIMITS["trial"] == 1


@pytest.mark.unit
def test_paid_billing_tiers_include_all_live_sports():
    # Per the published plans, every paid billing tier unlocks all live sports.
    for tier in PRICE_MAP:
        assert max_sports_for_tier(tier) == len(CHOOSABLE_SPORTS), (
            f"paid tier {tier!r} should include all {len(CHOOSABLE_SPORTS)} live "
            f"sports, got {max_sports_for_tier(tier)}"
        )
