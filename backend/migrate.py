"""
Idempotent migration runner. Applies any backend/migrations/*.sql not yet recorded
in the schema_migrations table. Safe to run repeatedly and across deploys.

Run via Railway preDeployCommand: `python -m backend.migrate`
"""
import asyncio
import os
import pathlib

import asyncpg

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"
# Migrations at or below this number are assumed already applied on existing
# databases (they were run manually before the runner existed). Used only to
# seed the tracking table on first run so we never re-run CREATE TABLE on a
# live DB.
BASELINE_MAX = "006"
ADVISORY_LOCK_KEY = 778899  # arbitrary, shared across replicas


async def run():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        # Serialize across replicas / concurrent boots
        await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_KEY)

        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )

        applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        # First-run baseline: if nothing tracked yet but the DB is already
        # provisioned, mark pre-existing migrations as applied without running.
        if not applied:
            db_provisioned = await conn.fetchval("SELECT to_regclass('public.games')")
            if db_provisioned:
                for f in files:
                    if f.name[:3] <= BASELINE_MAX:
                        await conn.execute(
                            "INSERT INTO schema_migrations(filename) VALUES($1) ON CONFLICT DO NOTHING",
                            f.name,
                        )
                applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
                print(f"[migrate] baselined existing DB: marked <= {BASELINE_MAX} as applied")

        ran = 0
        for f in files:
            if f.name in applied:
                continue
            sql = f.read_text(encoding="utf-8")
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations(filename) VALUES($1) ON CONFLICT DO NOTHING",
                f.name,
            )
            print(f"[migrate] applied {f.name}")
            ran += 1

        if ran == 0:
            print("[migrate] no pending migrations")
        else:
            print(f"[migrate] done, {ran} migration(s) applied")
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)
        except Exception:
            pass
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
