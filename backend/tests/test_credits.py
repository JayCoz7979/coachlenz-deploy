"""
Analysis-credit model (pure): locked per-analysis credit costs, bundle catalog, the
spend bucket math, and the 65% margin-floor helper.
"""
from backend.services import credits as C


def test_split_spend_bucket_order_and_insufficient():
    assert C.split_spend(0, 30, 29) == (0, 29)       # drawn from the purchased wallet
    assert C.split_spend(0, 0, 1) is None
    assert C.split_spend(0, 28, 29) is None          # one short
    assert C.split_spend(5, 5, 0) == (0, 0)


def test_segment_credits_are_prorated_and_margin_neutral():
    # Football deep = 55. A 12-min slice of a 48-min game = 25% -> ceil(55*.25)=14.
    assert C.segment_credits("football", deep=True, full_seconds=48 * 60, segment_seconds=12 * 60) == 14
    # Basketball deep = 60. Half the film -> 30.
    assert C.segment_credits("basketball", deep=True, full_seconds=3600, segment_seconds=1800) == 30
    # A tiny slice is floored (never charged near-zero).
    assert C.segment_credits("football", deep=True, full_seconds=97 * 60, segment_seconds=5 * 60) == C.SEGMENT_MIN_CREDITS
    # A full-length "segment" is never more than the full run.
    assert C.segment_credits("football", deep=True, full_seconds=2880, segment_seconds=2880) == 55
    # Unknown film length -> fall back to the full cost (no unfair discount).
    assert C.segment_credits("football", deep=True, full_seconds=None, segment_seconds=720) == 55
    assert C.segment_credits("football", deep=True, full_seconds=0, segment_seconds=720) == 55


def test_locked_credit_costs():
    # Standard by sport
    assert C.credits_for(sport="football", deep=False, is_rerun=False) == 29
    assert C.credits_for(sport="basketball", deep=False, is_rerun=False) == 27
    assert C.credits_for(sport="flag", deep=False, is_rerun=False) == 22
    # Deep + grade by sport
    assert C.credits_for(sport="football", deep=True, is_rerun=False) == 55
    assert C.credits_for(sport="basketball", deep=True, is_rerun=False) == 60  # provisional
    # Re-analysis is flat regardless of sport/depth
    assert C.credits_for(sport="football", deep=True, is_rerun=True) == 9
    # Unknown sport falls back to the football cost (safe, highest)
    assert C.credits_for(sport="soccer", deep=False, is_rerun=False) == 29
    assert C.credits_for(sport=None, deep=True, is_rerun=False) == 55


def test_bundles_catalog_and_descending_per_credit():
    assert C.BUNDLES["starter"] == (30, 2900)
    assert C.BUNDLES["sideline"] == (100, 8900)
    assert C.BUNDLES["season"] == (250, 19900)
    assert C.BUNDLES["program"] == (500, 36900)
    assert C.BUNDLES["department"] == (1000, 69900)
    # Per-credit price must fall as bundles get bigger.
    per = [p / c for c, p in C.BUNDLES.values()]
    assert per == sorted(per, reverse=True)
    # Cheapest credit is the Department price used for the margin floor.
    assert round(min(per) / 100, 2) == C.FLOOR_CREDIT_PRICE


def test_margin_floor_ceilings():
    # Max compute cost per run to hold 65% at the cheapest ($0.70) credit price.
    assert C.max_cogs_at_floor(29) == 7.105    # standard football
    assert C.max_cogs_at_floor(55) == 13.475   # deep+grade football
    assert C.max_cogs_at_floor(9) == 2.205     # re-analysis
    assert C.MARGIN_FLOOR == 0.65


def test_margin_verdict_bands():
    # Deep+grade football = 55 credits -> $38.50 revenue at the $0.70 floor.
    assert C.margin_verdict(10.0, 55) == "pass"      # ~74% margin
    assert C.margin_verdict(13.475, 55) == "pass"    # exactly 65%
    assert C.margin_verdict(16.0, 55) == "watch"     # ~58%
    assert C.margin_verdict(20.0, 55) == "fail"      # ~48% (thin/loss risk)
    assert C.margin_verdict(5.0, 0) == "no_data"


def test_subscription_tiers_are_access_only():
    assert C.SUBSCRIPTION_TIERS["coach"]["monthly_cents"] == 999
    assert C.SUBSCRIPTION_TIERS["athletic_dept"]["monthly_cents"] == 2999
    # No monthly credit grant exists in the model.
    assert not hasattr(C, "PLAN_MONTHLY_CREDITS")
    assert not hasattr(C, "grant_monthly")
