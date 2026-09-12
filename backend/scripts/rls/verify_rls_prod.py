"""
Read-only RLS readiness / state verifier for the Stage 4 cutover checklist.

Touches nothing (SELECTs only). Run before enabling (readiness), after enabling
(confirm inert while the app is still `postgres`), and after the cutover (confirm
enforcing). Run so the Postgres service env is injected:

  railway run --service Postgres -- python backend/scripts/rls/verify_rls_prod.py

Reports:
  1. the app_rls role's attributes (must be canlogin once you set the password,
     NOSUPERUSER, NOBYPASSRLS);
  2. RLS coverage: org-scoped tables vs. those with the org_isolation policy + FORCE;
  3. grant gaps: any org-scoped table app_rls cannot SELECT/INSERT/UPDATE/DELETE;
  4. whether RLS is currently ON for any org table (so you can tell inert vs. live).
"""
import os, sys, io, asyncio

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def main():
    import asyncpg
    dsn = (os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        db = await conn.fetchval("SELECT current_database()")
        print(f"database: {db}\n")

        # 1. app_rls role attributes
        r = await conn.fetchrow("SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname='app_rls'")
        if not r:
            print("1. app_rls role: MISSING (run migration 031 first)")
        else:
            ok = (not r["rolsuper"]) and (not r["rolbypassrls"])
            print(f"1. app_rls role: canlogin={r['rolcanlogin']}  superuser={r['rolsuper']}  bypassrls={r['rolbypassrls']}  "
                  f"-> {'OK (NOSUPERUSER, NOBYPASSRLS)' if ok else 'PROBLEM: must be NOSUPERUSER + NOBYPASSRLS'}")
            if not r["rolcanlogin"]:
                print("   (canlogin=False -> still NOLOGIN; set the password before cutover: ALTER ROLE app_rls LOGIN PASSWORD '...')")

        # 2. RLS coverage
        org_tables = [x["t"] for x in await conn.fetch(
            "SELECT table_name AS t FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name='organization_id' ORDER BY table_name")]
        policied = {x["tablename"] for x in await conn.fetch(
            "SELECT tablename FROM pg_policies WHERE schemaname='public' AND policyname='org_isolation'")}
        forced = {x["relname"] for x in await conn.fetch(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relrowsecurity AND c.relforcerowsecurity")}
        missing_policy = [t for t in org_tables if t not in policied]
        print(f"\n2. coverage: {len(org_tables)} org-scoped tables | "
              f"{len(policied)} with org_isolation policy | {len(forced)} ENABLE+FORCE")
        print(f"   org tables WITHOUT the policy: {missing_policy or 'none'}")

        # 3. grant gaps
        gaps = []
        for t in org_tables:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                has = await conn.fetchval("SELECT has_table_privilege('app_rls', $1, $2)", f"public.{t}", priv)
                if not has:
                    gaps.append(f"{t}:{priv}")
        print(f"\n3. app_rls grant gaps: {gaps or 'none (app_rls can DML every org table)'}")

        # 4. live vs inert
        any_on = [x["relname"] for x in await conn.fetch(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relrowsecurity AND c.relname = ANY($1::text[])", org_tables)]
        print(f"\n4. RLS currently ENABLED on {len(any_on)}/{len(org_tables)} org tables"
              f" -> {'INERT until a service connects as app_rls (postgres bypasses)' if any_on else 'not enabled yet'}")

        # Phase-aware summary. A real BLOCKER is only a bad role or a grant gap; missing
        # policies / not-yet-LOGIN are expected pending steps, not problems.
        role_bad = (not r) or r["rolsuper"] or r["rolbypassrls"]
        print("\nREADINESS:")
        if role_bad:
            print("  BLOCKER: app_rls missing or not NOSUPERUSER/NOBYPASSRLS — fix before anything else.")
        if gaps:
            print("  BLOCKER: app_rls grant gaps above — run Step 2 (grant_app_rls.sql).")
        if not role_bad and not gaps:
            print("  Groundwork OK (role + grants).")
            if r and not r["rolcanlogin"]:
                print("  PENDING Step 1: set app_rls LOGIN password.")
            if missing_policy:
                print("  PENDING Step 3: policies not applied yet (run stage3_enable_rls.sql).")
            elif not any_on:
                print("  Policies present but RLS disabled (rolled back / pre-enable).")
            else:
                print("  RLS enabled on all org tables. Enforcing for any service on the app_rls role.")
    finally:
        await conn.close()


asyncio.run(main())
