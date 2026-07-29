"""
Sport entitlement lock — tier limits + enforcement.

Run:  DATABASE_URL=... SECRET_KEY=... ANTHROPIC_API_KEY=... python -m backend.tests.test_sports_lock
"""
from types import SimpleNamespace
from fastapi import HTTPException

from backend.services.sports import (
    max_sports_for_tier, sport_allowed, assert_sport_allowed, chosen_sports,
    CHOOSABLE_SPORTS,
)


def ORG(tier="trial", sports=None):
    return SimpleNamespace(subscription_tier=tier, chosen_sports=sports or [])


def run():
    # ── tier -> how many sports (real billing vocabulary) ────────────────────
    all_sports = len(CHOOSABLE_SPORTS)
    assert max_sports_for_tier("trial") == 1, "trial is single-sport"
    assert max_sports_for_tier("coach") == all_sports, "Coach plan includes All sports"
    assert max_sports_for_tier("athletic_dept") == all_sports
    assert max_sports_for_tier("district") == all_sports
    assert max_sports_for_tier("who_knows") == 1, "unknown tier defaults to 1 (most restrictive)"
    assert max_sports_for_tier(None) == 1
    print(f"  tier limits: trial=1, coach/athletic_dept/district=all({all_sports}), unknown=1  OK")

    # ── not yet locked (empty) = allow everything (legacy / pre-onboarding) ──
    fresh = ORG(sports=[])
    assert sport_allowed(fresh, "basketball") and sport_allowed(fresh, "football")
    assert_sport_allowed(fresh, "football")  # must NOT raise
    print("  empty chosen_sports -> unrestricted (backward compatible)  OK")

    # ── locked to basketball: basketball allowed, football warned ────────────
    bball = ORG(tier="coach", sports=["basketball"])
    assert sport_allowed(bball, "basketball")
    assert not sport_allowed(bball, "football")
    assert_sport_allowed(bball, "basketball")  # allowed
    raised = None
    try:
        assert_sport_allowed(bball, "football")
    except HTTPException as e:
        raised = e
    assert raised is not None and raised.status_code == 403, "wrong-sport must 403"
    assert "locked to Basketball" in raised.detail and "Football" in raised.detail
    print(f"  locked to basketball -> football blocked (403): \"{raised.detail[:70]}...\"  OK")

    # ── two-sport plan honored ──────────────────────────────────────────────
    both = ORG(tier="coach", sports=["basketball", "football"])
    assert_sport_allowed(both, "basketball")
    assert_sport_allowed(both, "football")
    try:
        assert_sport_allowed(both, "volleyball")
        assert False, "volleyball should be blocked"
    except HTTPException as e:
        assert e.status_code == 403
    print("  two-sport plan: both allowed, third blocked  OK")

    print("\nALL SPORT-LOCK ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
