from datetime import datetime, timedelta
from sqlalchemy import update
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


async def reserve_trial_game_slot(db, org: Organization) -> bool:
    """Atomically claim a trial game slot. Returns True if the caller may proceed,
    False if the trial limit is already spent.

    `can_upload_game` above is only a friendly pre-check: it reads a snapshot of
    `trial_games_used`, so N concurrent uploads all see the same value and all
    pass the `< LIMIT` gate — then each does a separate `+1`, blowing past the
    cap (multiple full detection runs on a 1-film trial). This gate is the
    authoritative one: a single conditional UPDATE takes a row lock and only
    increments while still under the limit, so the database serializes concurrent
    callers and at most LIMIT reservations can ever succeed. Call inside the same
    transaction that creates the game so a later failure rolls the reservation
    back with it. Paid/expired orgs are unaffected (no per-game trial cap)."""
    if not is_trial_active(org):
        return True
    res = await db.execute(
        update(Organization)
        .where(Organization.id == org.id,
               Organization.trial_games_used < TRIAL_GAME_LIMIT)
        .values(trial_games_used=Organization.trial_games_used + 1)
    )
    return (res.rowcount or 0) > 0

def is_feature_locked(org: Organization, feature: str) -> bool:
    if not is_trial_active(org):
        return False
    return feature in TRIAL_LOCKED_FEATURES

def get_trial_days_remaining(org: Organization) -> int:
    if not org.trial_ends_at:
        return 0
    delta = to_naive_utc(org.trial_ends_at) - datetime.utcnow()
    return max(0, delta.days)
