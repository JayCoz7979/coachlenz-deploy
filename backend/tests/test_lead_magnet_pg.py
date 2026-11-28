"""Real-Postgres test for 067_lead_magnet_leads.sql (the Halftime Sheet PDF leads table).

Skipped unless MIGRATIONS_TEST_DATABASE_URL is set (same switch as
test_live_game_report_type_pg.py). DESTRUCTIVE to that database: it drops and
recreates the public schema, so point it only at a throwaway Postgres.
"""
import asyncio
import os

import pytest

_URL = os.environ.get("MIGRATIONS_TEST_DATABASE_URL")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not _URL, reason="MIGRATIONS_TEST_DATABASE_URL is not set")]


def _norm(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").rstrip("/")


async def _fresh_schema_with_all_migrations(conn):
    from backend.migrate import MIGRATIONS_DIR
    await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
    await conn.execute("CREATE SCHEMA public")
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        await conn.execute(f.read_text(encoding="utf-8"))


def test_067_table_defaults_unique_email_and_down():
    import asyncpg
    from backend.migrate import MIGRATIONS_DIR

    async def run():
        conn = await asyncpg.connect(_norm(_URL))
        try:
            await _fresh_schema_with_all_migrations(conn)
            # Re-applying is a no-op (idempotent).
            await conn.execute((MIGRATIONS_DIR / "067_lead_magnet_leads.sql").read_text())

            row = await conn.fetchrow(
                "INSERT INTO lead_magnet_leads (name, email, download_token) "
                "VALUES ('Test Coach', 'coach@coachmail.com', 'tok1') "
                "RETURNING source, phone, created_at, consent_email")
            assert row["source"] == "halftime_pdf"
            assert row["phone"] is None
            assert row["created_at"] is not None
            assert row["consent_email"] is False

            # Same email, different case, same source -> unique violation.
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO lead_magnet_leads (name, email, download_token) "
                    "VALUES ('Test Coach', 'COACH@coachmail.com', 'tok2')")
            # Duplicate download token -> unique violation.
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO lead_magnet_leads (name, email, download_token) "
                    "VALUES ('Other Coach', 'other@coachmail.com', 'tok1')")
            # Name + email + token are required; phone is not.
            with pytest.raises(asyncpg.NotNullViolationError):
                await conn.execute(
                    "INSERT INTO lead_magnet_leads (email, download_token) VALUES ('a@b.com', 'tok3')")

            await conn.execute((MIGRATIONS_DIR / "down" / "067_lead_magnet_leads.down.sql").read_text())
            assert await conn.fetchval("SELECT to_regclass('public.lead_magnet_leads')") is None
        finally:
            await conn.close()

    asyncio.run(run())


def test_067_matches_the_orm_model():
    """Every ORM column exists in the migrated table."""
    import asyncpg
    from backend.models.lead_magnet import LeadMagnetLead

    async def run():
        conn = await asyncpg.connect(_norm(_URL))
        try:
            await _fresh_schema_with_all_migrations(conn)
            cols = {r["column_name"] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name='lead_magnet_leads'")}
        finally:
            await conn.close()
        assert {c.name for c in LeadMagnetLead.__table__.columns} <= cols

    asyncio.run(run())
