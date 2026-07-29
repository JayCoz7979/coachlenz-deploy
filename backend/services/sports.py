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

# How many sports each BILLING tier may lock in at onboarding. The live billing
# tiers are coach / athletic_dept / district (see billing.PRICE_MAP) plus the
# contact-sales `enterprise` and the `trial`. Per the published plans (the Coach
# plan lists "All sports"; higher plans are "Everything in Coach/..."), every PAID
# tier unlocks all live sports; only the 2-game trial is single-sport.
#
# This MUST stay in sync with billing.PRICE_MAP: a paid tier missing here silently
# falls through to DEFAULT_SPORT_LIMIT (1) and caps a paying org at one sport
# (this was bug I-1). test_tier_billing_coverage.py enforces the invariant.
# Unknown tiers still default to 1 (safest, most-restrictive).
ALL_SPORTS = len(CHOOSABLE_SPORTS)  # "All sports" == every sport with a live engine
TIER_SPORT_LIMITS = {
    "trial": 1,                    # 2-game trial: one sport
    "coach": ALL_SPORTS,           # Coach plan explicitly includes "All sports"
    "athletic_dept": ALL_SPORTS,   # "Everything in Coach" + multi-team
    "district": ALL_SPORTS,        # "Everything in Athletic Dept" + district-wide
    "enterprise": ALL_SPORTS,      # "Everything in District" (contact sales)
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
