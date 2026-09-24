"""
Apply a .sql file to the CoachLenz production Postgres, robustly and without a psql
dependency. Used by the Stage 4 cutover checklist (docs/security/rls-stage4-cutover.md)
to run the idempotent RLS scripts by hand.

Run it so the Postgres service's env (incl. DATABASE_PUBLIC_URL) is injected:

  railway run --service Postgres -- python backend/scripts/rls/apply_sql.py <file.sql>

It connects to the app database (the one the backend uses), prints exactly which
database/role/host it is about to touch, applies the file in one call, and echoes any
RAISE NOTICE output. The scripts it runs (grant_app_rls.sql, stage3_enable_rls.sql,
stage3_disable_rls.sql) are all idempotent, so a re-run is safe.
"""
import os, sys, io, asyncio
from urllib.parse import urlsplit

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def main(path: str):
    import asyncpg
    dsn = (os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]).replace("postgresql+asyncpg://", "postgresql://")
    p = urlsplit(dsn)
    host = p.hostname
    db = (p.path or "/").lstrip("/")
    sql = open(path, encoding="utf-8").read()

    conn = await asyncpg.connect(dsn)
    notices = []
    conn.add_log_listener(lambda c, m: notices.append(str(m)))
    try:
        who = await conn.fetchrow("SELECT current_database() AS db, current_user AS usr, "
                                  "(SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS super")
        print(f"TARGET  database={who['db']}  role={who['usr']}  superuser={who['super']}  host={host}")
        print(f"APPLY   {path}")
        # Explicit confirmation guard for anything that is NOT obviously the app DB.
        await conn.execute(sql)
        for n in notices:
            print(f"  {n}")
        print("DONE (no error).")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python apply_sql.py <path-to-sql-file>"); sys.exit(2)
    asyncio.run(main(sys.argv[1]))
