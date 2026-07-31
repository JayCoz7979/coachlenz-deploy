"""
RLS mechanism proof-of-concept + tenant-table inventory.

CI runs integration tests on SQLite, which has no Row Level Security, so the RLS
policy + session-GUC mechanism can never be validated there. This script proves
it against a REAL Postgres, in a fully isolated throwaway schema with a real
NOSUPERUSER role, then cleans everything up. It touches no application tables.

It proves five things the RLS backstop depends on:
  1. As a non-superuser with NO org context set, RLS returns ZERO rows (fail-closed).
  2. With app.org_id set to org A, only org A's rows are visible.
  3. Switching app.org_id to org B flips visibility to org B only.
  4. An INSERT that violates the policy (wrong org) is REJECTED by WITH CHECK.
  5. A SUPERUSER connection BYPASSES RLS entirely (why prod is inert until the
     DATABASE_URL is cut over to the restricted role).

Run:  PGURL=<superuser public url> python -m backend.tests.rls_poc
"""
import asyncio
import os
import asyncpg

POC_SCHEMA = "rls_poc"
POC_ROLE = "app_rls_poc"
POC_PW = "poc_only_ephemeral_pw"

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def tenant_table_inventory(su):
    """Every table carrying an organization_id column = a table RLS must cover."""
    rows = await su.fetch(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name='organization_id' "
        "ORDER BY table_name"
    )
    tables = [r["table_name"] for r in rows]
    print(f"\nTENANT TABLES (organization_id present): {len(tables)}")
    for t in tables:
        print(f"  - {t}")
    return tables


async def run():
    su_url = os.environ["PGURL"].replace("postgresql+asyncpg://", "postgresql://")
    su = await asyncpg.connect(su_url)
    role_conn = None
    try:
        await tenant_table_inventory(su)

        # ── Build an isolated POC world (throwaway schema + restricted role) ──
        await su.execute(f"DROP SCHEMA IF EXISTS {POC_SCHEMA} CASCADE")
        await su.execute(f"CREATE SCHEMA {POC_SCHEMA}")
        await su.execute(
            f"CREATE TABLE {POC_SCHEMA}.games "
            f"(id serial primary key, organization_id uuid not null, title text)"
        )
        await su.execute(
            f"INSERT INTO {POC_SCHEMA}.games (organization_id, title) VALUES "
            f"('{ORG_A}','A film 1'),('{ORG_A}','A film 2'),('{ORG_B}','B secret')"
        )
        await su.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{POC_ROLE}') "
            f"THEN CREATE ROLE {POC_ROLE} LOGIN PASSWORD '{POC_PW}' NOSUPERUSER NOBYPASSRLS; "
            f"END IF; END $$;"
        )
        await su.execute(f"GRANT USAGE ON SCHEMA {POC_SCHEMA} TO {POC_ROLE}")
        await su.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {POC_SCHEMA}.games TO {POC_ROLE}")
        await su.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {POC_SCHEMA} TO {POC_ROLE}")

        # ── Enable + FORCE RLS + the org-isolation policy ──
        await su.execute(f"ALTER TABLE {POC_SCHEMA}.games ENABLE ROW LEVEL SECURITY")
        await su.execute(f"ALTER TABLE {POC_SCHEMA}.games FORCE ROW LEVEL SECURITY")
        await su.execute(
            f"CREATE POLICY org_isolation ON {POC_SCHEMA}.games "
            f"USING (organization_id = current_setting('app.org_id', true)::uuid) "
            f"WITH CHECK (organization_id = current_setting('app.org_id', true)::uuid)"
        )

        # ── Superuser bypass check (proves why prod is inert pre-cutover) ──
        n_su = await su.fetchval(f"SELECT count(*) FROM {POC_SCHEMA}.games")
        check("superuser BYPASSES rls (sees all 3 rows)", n_su == 3)

        # ── Connect AS the restricted role and exercise the policy ──
        role_url = su_url
        # swap credentials in the URL: postgresql://user:pw@host/db
        # rebuild with the poc role + pw, same host/db.
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(su_url)
        netloc = f"{POC_ROLE}:{POC_PW}@{parts.hostname}:{parts.port}"
        role_url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        role_conn = await asyncpg.connect(role_url)

        # 1. no context -> fail closed
        n0 = await role_conn.fetchval(f"SELECT count(*) FROM {POC_SCHEMA}.games")
        check("no app.org_id -> 0 rows (fail-closed)", n0 == 0)

        # 2. org A context -> only A
        await role_conn.execute(f"SET app.org_id = '{ORG_A}'")
        rowsA = await role_conn.fetch(f"SELECT title FROM {POC_SCHEMA}.games")
        check("org A context -> only A's 2 rows", len(rowsA) == 2 and all(r["title"].startswith("A") for r in rowsA))

        # 3. switch to org B -> only B
        await role_conn.execute(f"SET app.org_id = '{ORG_B}'")
        rowsB = await role_conn.fetch(f"SELECT title FROM {POC_SCHEMA}.games")
        check("org B context -> only B's 1 row", len(rowsB) == 1 and rowsB[0]["title"] == "B secret")

        # 4. cross-org INSERT rejected by WITH CHECK (context=B, insert as A)
        rejected = False
        try:
            await role_conn.execute(
                f"INSERT INTO {POC_SCHEMA}.games (organization_id, title) VALUES ('{ORG_A}','sneaky')"
            )
        except asyncpg.exceptions.InsufficientPrivilegeError:
            # Postgres reports an RLS WITH CHECK violation as 42501 (insufficient
            # privilege), not a CHECK-constraint violation.
            rejected = True
        check("cross-org INSERT rejected by WITH CHECK", rejected)

        # 5. a legit same-org insert (context=B, insert as B) succeeds
        await role_conn.execute(
            f"INSERT INTO {POC_SCHEMA}.games (organization_id, title) VALUES ('{ORG_B}','B legit')"
        )
        nB2 = await role_conn.fetchval(f"SELECT count(*) FROM {POC_SCHEMA}.games")
        check("same-org INSERT allowed (B now sees 2)", nB2 == 2)

    finally:
        if role_conn is not None:
            await role_conn.close()
        # Cleanup: drop the throwaway schema + role. Never leave POC artifacts behind.
        try:
            await su.execute(f"DROP SCHEMA IF EXISTS {POC_SCHEMA} CASCADE")
            await su.execute(f"DROP ROLE IF EXISTS {POC_ROLE}")
        except Exception as e:
            print(f"[cleanup warning] {e}")
        await su.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", ", ".join(FAIL))
        raise SystemExit(1)
    print("RLS MECHANISM PROVEN")


if __name__ == "__main__":
    asyncio.run(run())
