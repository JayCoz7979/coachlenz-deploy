from datetime import datetime, timedelta
from backend.models.organization import Organization
from backend.utils.timeutils import to_naive_utc

TRIAL_LOCKED_FEATURES = {"advanced_tendencies", "multi_game_reports", "film_packages", "coach_tenure"}
TRIAL_GAME_LIMIT = 1
TRIAL_DAYS = 14

def is_trial_active(org: Organization) -> bool:
    if not org.is_trial:
        return False
    if org.trial_ends_at and datetime.utcnow() > to_naive_utc(org.trial_ends_at):
        return False
    return True

def can_upload_game(org: Organization) -> bool:
    if not is_trial_active(org):
        return True
    return org.trial_games_used < TRIAL_GAME_LIMIT

def is_feature_locked(org: Organization, feature: str) -> bool:
    if not is_trial_active(org):
        return False
    return feature in TRIAL_LOCKED_FEATURES

def get_trial_days_remaining(org: Organization) -> int:
    if not org.trial_ends_at:
        return 0
    delta = to_naive_utc(org.trial_ends_at) - datetime.utcnow()
    return max(0, delta.days)
