"""
Seed / reset a pre-verified TEST account that lands on the onboarding "Choose your
sport" step, so the onboarding UI (and the "See example reports" link there) can be
exercised without real email/phone verification codes.

The account is created with email_verified + phone_verified = True, onboarding NOT
completed, and no sport chosen, so GET /onboarding/status returns
next_step = "choose_sport" and the app drops the user on that step after login.

Runs in the backend environment (needs the app deps + DATABASE_URL). Example:

    TEST_ACCOUNT_PASSWORD='pick-a-strong-one' python -m backend.seed_test_account

Idempotent: re-running RESETS the account back to the sport step (re-verified, no sport,
onboarding incomplete + password re-set) so you can walk onboarding again. The account
holds no real data; it exists only to reach the onboarding UI.
"""
import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.models.base import AsyncSessionLocal
from backend.models.organization import Organization
from backend.models.user import User
from backend.services.auth import hash_password  # same hashing the login path verifies

EMAIL = os.environ.get("TEST_ACCOUNT_EMAIL", "livetest@coachlenz.test")
NAME = os.environ.get("TEST_ACCOUNT_NAME", "Live Test Coach")
PHONE = os.environ.get("TEST_ACCOUNT_PHONE", "+15555550100")  # placeholder; never texted
SLUG = "live-test-account"


async def run() -> None:
    pw = os.environ.get("TEST_ACCOUNT_PASSWORD", "")
    if len(pw) < 8:
        raise SystemExit("Set TEST_ACCOUNT_PASSWORD (>= 8 chars) before running.")

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == EMAIL))
        user = res.scalar_one_or_none()

        if user:
            org = await db.get(Organization, user.organization_id)
            # Reset to the sport step so onboarding can be walked again.
            org.onboarding_completed = False
            org.chosen_sports = []
            flag_modified(org, "chosen_sports")
            user.email_verified = True
            user.phone_verified = True
            user.phone = PHONE
            user.role = "owner"           # owner may choose the plan's sport(s)
            user.is_active = True
            user.hashed_password = hash_password(pw)
            await db.commit()
            action = "reset"
        else:
            org = Organization(
                name="Live Test", slug=SLUG, subscription_tier="trial", is_trial=True,
                trial_ends_at=datetime.utcnow() + timedelta(days=14),
            )
            db.add(org)
            await db.flush()
            user = User(
                organization_id=org.id, name=NAME, email=EMAIL,
                hashed_password=hash_password(pw), role="owner",
                email_verified=True, phone_verified=True, phone=PHONE, is_active=True,
            )
            db.add(user)
            await db.commit()
            action = "created"

    print(f"✓ Test account {action}: {EMAIL}")
    print("  Log in with that email + your TEST_ACCOUNT_PASSWORD.")
    print("  You'll land on the onboarding 'Choose your sport' step; the")
    print("  'See example reports' link is directly under the Continue button.")


if __name__ == "__main__":
    asyncio.run(run())
