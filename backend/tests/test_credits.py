"""
Analysis-credit bucket math (pure) + config sanity. The DB wrappers in
services/credits.py are thin around split_spend; this locks the critical logic.
"""
from backend.services import credits as C


def test_split_spend_takes_included_first():
    assert C.split_spend(2, 3, 1) == (1, 0)
    assert C.split_spend(2, 3, 2) == (2, 0)


def test_split_spend_spills_into_purchased():
    assert C.split_spend(1, 5, 3) == (1, 2)
    assert C.split_spend(0, 3, 1) == (0, 1)


def test_split_spend_insufficient_returns_none():
    assert C.split_spend(0, 0, 1) is None
    assert C.split_spend(1, 0, 2) is None
    assert C.split_spend(2, 2, 5) is None


def test_split_spend_zero_is_noop():
    assert C.split_spend(5, 5, 0) == (0, 0)
    assert C.split_spend(0, 0, 0) == (0, 0)


def test_monthly_credits_for_known_and_unknown_tiers():
    assert C.monthly_credits_for("coach") == 2
    assert C.monthly_credits_for("athletic_dept") == 6
    assert C.monthly_credits_for("district") == 30
    assert C.monthly_credits_for("enterprise") == 300
    assert C.monthly_credits_for("COACH") == 2          # case-insensitive
    assert C.monthly_credits_for("trial") == 0          # not a paid tier
    assert C.monthly_credits_for(None) == 0


def test_packs_priced_above_unit_cost():
    # Each pack must price a credit above the ~$50 COGS so a top-up never loses money.
    for pack_id, (credits, price_cents) in C.PACKS.items():
        assert credits > 0 and price_cents > 0
        assert price_cents / credits >= 5000, f"{pack_id} prices a credit below $50 COGS"
