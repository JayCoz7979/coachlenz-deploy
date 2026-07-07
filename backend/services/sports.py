"""
Sport entitlement policy — the "one sport per tier, locked in" rule.

During onboarding a client picks the sport(s) their plan allows. That choice is
stored on the organization (organizations.chosen_sports) and LOCKED: every
film-analysis entry point (film import, game creation, scout sessions) checks the
sport against this list, so a coach on a single-sport plan cannot flip-flop and
diagnose film from a sport they did not buy. The tier decides HOW MANY sports they
may pick.

Backward-compatible: an org with an empty chosen_sports (pre-onboarding / legacy)
is NOT restricted — enforcement only kicks in once a sport has been locked in.
"""
from typing import List
from fastapi import HTTPException

# Sports with a real analysis engine that a client may lock onto today.
CHOOSABLE_SPORTS = ["football", "flag_football", "basketball"]
# Everything the platform will accept as a sport value (engines + roadmap stubs).
VALID_SPORTS = CHOOSABLE_SPORTS + ["volleyball", "baseball"]

# Human labels for the UI / warnings.
SPORT_LABELS = {
    "football": "Football",
    "flag_football": "Flag Football",
    "basketball": "Basketball",
    "volleyball": "Volleyball",
    "baseball": "Baseball",
}

# How many sports each plan tier may lock in. First tier = ONE sport.
# Unknown tiers default to 1 (the safest, most-restrictive assumption).
TIER_SPORT_LIMITS = {
    "trial": 1,
    "starter": 1,
    "tier1": 1,
    "pro": 2,
    "tier2": 2,
    "premium": 3,
    "elite": 99,
    "enterprise": 99,
    "tier3": 99,
    "unlimited": 99,
}
DEFAULT_SPORT_LIMIT = 1


def label(sport: str) -> str:
    return SPORT_LABELS.get(sport, (sport or "").replace("_", " ").title())


def max_sports_for_tier(tier: str) -> int:
    """How many sports a plan tier is entitled to lock in."""
    return TIER_SPORT_LIMITS.get((tier or "").strip().lower(), DEFAULT_SPORT_LIMIT)


def chosen_sports(org) -> List[str]:
    return list(getattr(org, "chosen_sports", None) or [])


def is_locked(org) -> bool:
    """True once the org has completed sport selection (enforcement active)."""
    return len(chosen_sports(org)) > 0


def sport_allowed(org, sport: str) -> bool:
    """Allowed if the org hasn't locked a sport yet (legacy/pre-onboarding) OR the
    sport is one of the locked-in sports."""
    locked = chosen_sports(org)
    if not locked:
        return True
    return (sport or "").strip().lower() in locked


def assert_sport_allowed(org, sport: str):
    """Guard for every film-analysis entry point. Raises a 403 the frontend shows
    as a plain-English warning when a coach tries a sport outside their plan."""
    if sport_allowed(org, sport):
        return
    locked = chosen_sports(org)
    plan_sports = ", ".join(label(s) for s in locked) or "your plan"
    raise HTTPException(
        status_code=403,
        detail=(
            f"Your plan is locked to {plan_sports}. You tried to analyze "
            f"{label(sport)} film, which isn't included. Upgrade your plan to add "
            f"another sport, or import {plan_sports} film instead."
        ),
    )
