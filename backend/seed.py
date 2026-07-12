"""
Seed script — creates admin org + user at info@cosbyaisolutions.com.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.models.base import AsyncSessionLocal, engine, Base
from backend.models.organization import Organization
from backend.models.user import User
from backend.services.auth import hash_password
from sqlalchemy import select


async def seed():
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == "info@cosbyaisolutions.com"))
        if existing.scalar_one_or_none():
            print("Admin user already exists. Skipping seed.")
            return

        org = Organization(
            name="Cosby AI Solutions",
            slug="cosby-ai-admin",
            subscription_tier="district",
            is_trial=False,
            has_coach_tenure_access=True,
            admin_level="super",
        )
        db.add(org)
        await db.flush()

        # Fail closed: never seed the super-admin with the committed placeholder
        # password. This account has admin_level="super" (full /admin/* access).
        admin_pw = os.environ.get("ADMIN_PASSWORD", "")
        if not admin_pw or admin_pw == "ChangeMeNow!" or len(admin_pw) < 12:
            raise SystemExit(
                "Refusing to seed the super-admin: set a strong ADMIN_PASSWORD env "
                "(>= 12 chars, not the placeholder) before running the seed."
            )
        user = User(
            organization_id=org.id,
            name="Jay Cosby",
            email="info@cosbyaisolutions.com",
            hashed_password=hash_password(admin_pw),
            role="owner",
            email_verified=True,
        )
        db.add(user)

        await db.commit()
        print(f"✓ Admin org created: {org.id}")
        print(f"✓ Admin user: info@cosbyaisolutions.com")
        print("⚠️  Change ADMIN_PASSWORD before going live!")


if __name__ == "__main__":
    asyncio.run(seed())
