"""
Entitlement gates — the ONE place that turns the declared trial policy into 403s.

Two rules, enforced at every expensive / paid entry point so the policy can't
drift per-endpoint:

1. Paid-feature locks. `services.trial.TRIAL_LOCKED_FEATURES` already declares what
   a trial does NOT include (deep analysis, multi-game reports, film packages,
   coach tenure) — this module is what actually blocks them. Before this, the
   locks were dead code and a free trial received the entire paid product.

2. Verify-and-pick-a-sport gate. An ACTIVE TRIAL must have a verified email
   (chargeback protection) and a locked-in sport (the trial is single-sport)
   before it can burn analysis. This closes the hole where a user who skips
   onboarding got an unverified, any-sport, fully-featured trial.

Paid orgs and expired trials pass through untouched — every guard is a no-op
unless `is_trial_active(org)`.
"""
from fastapi import HTTPException

from backend.services.trial import is_trial_active, is_feature_locked
from backend.services import sports as sports_svc

# Plain-English, upgrade-oriented copy the frontend can show verbatim.
_FEATURE_MSG = {
    "advanced_tendencies": (
        "Deep analysis and technique grading are paid features. Your free trial "
        "includes the standard film breakdown. Upgrade to unlock the deep "
        "multi-pass engine and per-play grading."
    ),
    "multi_game_reports": (
        "Multi-game reports are a paid feature. Your free trial covers a "
        "single-game report. Upgrade to combine multiple games into one scouting "
        "report."
    ),
    "film_packages": (
        "Film packages are a paid feature. Upgrade to bundle and share clip "
        "packages with your staff and players."
    ),
    "coach_tenure": "Coach Tenure is a paid feature. Upgrade to unlock it.",
}


def assert_feature_allowed(org, feature: str) -> None:
    """403 if this feature is locked for the org's (active) trial."""
    if is_feature_locked(org, feature):
        raise HTTPException(
            status_code=403,
            detail=_FEATURE_MSG.get(feature, "This is a paid feature. Upgrade to unlock it."),
        )


def assert_ready_to_analyze(org, user) -> None:
    """Gate the analysis paths (upload, URL import, auto-detect trigger).

    For an ACTIVE TRIAL only: require a verified email and a locked-in sport
    before any film can be analyzed. No-op for paid orgs and expired trials."""
    if not is_trial_active(org):
        return
    if not getattr(user, "email_verified", False):
        raise HTTPException(
            status_code=403,
            detail=(
                "Verify your email to start analyzing film — check your inbox for "
                "the 6-digit code we sent you."
            ),
        )
    if not sports_svc.is_locked(org):
        raise HTTPException(
            status_code=403,
            detail=(
                "Pick your sport to get started. Finish onboarding to choose your "
                "plan's sport, then analyze your first film."
            ),
        )
