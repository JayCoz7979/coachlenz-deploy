"""F3: hand-run down migrations back up what they drop and clear their
schema_migrations row, so the migrator re-applies them on the next deploy.

The unit tests read the SQL. The integration test runs every down file
against a throwaway database on the CI Postgres.
"""
import asyncio
import os
import pathlib
import subprocess
import sys
import uuid

import pytest

MIG = pathlib.Path(__file__).resolve().parents[1] / "migrations"
DOWNS = [
    "060_legal_acceptance_user_agent",
    "059_role_branch_minor_track",
    "058_marketing_consent_events",
    "057_marketing_lead_waitlist",
    "056_games_r2_key_unique",
]


@pytest.mark.unit
@pytest.mark.parametrize("name", DOWNS)
def test_every_down_clears_its_schema_migrations_row(name):
    sql = (MIG / f"{name}.down.sql").read_text(encoding="utf-8")
    assert f"DELETE FROM schema_migrations WHERE filename = '{name}.sql';" in sql


@pytest.mark.unit
@pytest.mark.parametrize("name,backups", [
    ("057_marketing_lead_waitlist", ["marketing_leads_bak_057_"]),
    ("058_marketing_consent_events", ["marketing_consent_events_bak_058_", "email_suppressions_bak_058_", "marketing_leads_bak_058_"]),
    ("060_legal_acceptance_user_agent", ["legal_acceptances_ua_bak_060_"]),
])
def test_lossy_downs_back_up_first_inside_one_transaction(name, backups):
    sql = (MIG / f"{name}.down.sql").read_text(encoding="utf-8")
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert body.strip().startswith("BEGIN;") and body.strip().endswith("COMMIT;")
    first_drop = min(i for i in (body.find("DROP TABLE"), body.find("DROP COLUMN")) if i >= 0)
    for prefix in backups:
        assert 0 <= body.find(prefix) < first_drop
    assert "WARNING" in sql or "Drops" in sql


_URL = os.environ.get(
    "UPLOAD_TEST_DATABASE_URL",
    "postgresql+asyncpg://coachlenz:coachlenz@localhost:5432/coachlenz_upload_test",
).replace("postgresql+asyncpg://", "postgresql://", 1)


async def _admin():
    import asyncpg
    return await asyncpg.connect(_URL)


async def _probe():
    conn = await _admin()
    await conn.close()


@pytest.mark.integration
def test_downs_back_up_data_and_the_migrator_reapplies(tmp_path):
    import asyncpg

    try:
        asyncio.run(_probe())
    except Exception as exc:
        if os.environ.get("CI"):
            pytest.fail(f"Postgres is required in CI ({type(exc).__name__})")
        pytest.skip(f"Postgres is not reachable ({type(exc).__name__})")

    dbname = "migdown_" + uuid.uuid4().hex[:10]
    base, _, _ = _URL.rpartition("/")
    url = f"{base}/{dbname}"

    async def admin(sql):
        conn = await _admin()
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(admin(f'CREATE DATABASE "{dbname}"'))
    asyncio.run(admin("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') "
                      "THEN CREATE ROLE postgres; END IF; END $$"))
    env = dict(os.environ, DATABASE_URL=url)
    repo = MIG.parents[1]

    def migrate():
        out = subprocess.run([sys.executable, "-m", "backend.migrate"], cwd=repo, env=env,
                             capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        return out.stdout

    async def scenario():
        conn = await asyncpg.connect(url)
        try:
            lead = await conn.fetchval(
                "INSERT INTO marketing_leads(email, role, role_branch, unsubscribed_at, unsubscribe_token) "
                "VALUES ('qa+down@coachlenz.com', 'head_coach', 'coach', now(), 'tok') RETURNING id")
            await conn.execute(
                "INSERT INTO marketing_consent_events(lead_id, event_type, email, ip_address, user_agent) "
                "VALUES ($1, 'signup', 'qa+down@coachlenz.com', '203.0.113.1', 'UA')", lead)
            await conn.execute("INSERT INTO email_suppressions(email_sha256, reason) VALUES ('h', 'unsubscribe_link')")
            for name in DOWNS:
                await conn.execute((MIG / f"{name}.down.sql").read_text(encoding="utf-8"))
            left = await conn.fetchval(
                "SELECT count(*) FROM schema_migrations WHERE filename = ANY($1::text[])",
                [f"{n}.sql" for n in DOWNS])
            names = [r["tablename"] for r in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE tablename LIKE '%\\_bak\\_%' ORDER BY 1")]
            events_bak = [n for n in names if n.startswith("marketing_consent_events_bak_058_")][0]
            supp_bak = [n for n in names if n.startswith("email_suppressions_bak_058_")][0]
            leads_bak = [n for n in names if n.startswith("marketing_leads_bak_057_")][0]
            ev = await conn.fetchrow(f'SELECT ip_address, user_agent FROM "{events_bak}"')
            supp = await conn.fetchval(f'SELECT count(*) FROM "{supp_bak}"')
            ld = await conn.fetchrow(f'SELECT unsubscribe_token, unsubscribed_at FROM "{leads_bak}"')
            return left, ev, supp, ld
        finally:
            await conn.close()

    try:
        migrate()
        left, ev, supp, ld = asyncio.run(scenario())
        assert left == 0
        assert (ev["ip_address"], ev["user_agent"]) == ("203.0.113.1", "UA")
        assert supp == 1
        assert ld["unsubscribe_token"] == "tok" and ld["unsubscribed_at"] is not None
        again = migrate()
        for name in DOWNS:
            assert f"applied {name}.sql" in again
    finally:
        asyncio.run(admin(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
