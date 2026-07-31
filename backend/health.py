"""
Readiness check for the API. `/health` is liveness (the process is up); readiness
answers "can we actually serve?" by pinging the database. Railway's healthcheck
points at the readiness endpoint so a deploy whose Postgres is unreachable is not
promoted to healthy and left serving 500s.
"""
from sqlalchemy import text

from backend.models.base import engine


async def db_ready() -> tuple[bool, str | None]:
    """Ping the database with SELECT 1. Returns (ok, error_message)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:  # connection refused, auth, DNS, etc.
        return False, str(e)[:200]
