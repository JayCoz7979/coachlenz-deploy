"""
Proves the Stage 2 org-context plumbing actually stamps app.org_id on the REAL
async engine + SQLAlchemy after_begin listener. CI runs on SQLite (no GUCs), so
this is validated manually against the production Postgres. It only ever reads
current_setting(); it touches no tables and writes nothing.

It proves:
  1. RLS_ENABLED False  -> listener is a no-op (app.org_id stays unset/NULL).
  2. RLS_ENABLED True, no context -> app.org_id = '' (fail-closed empty).
  3. With an org context   -> app.org_id echoes it.
  4. Across a COMMIT (new transaction) -> the org is re-applied automatically.

Run:  PGURL=<superuser public url> python -m backend.tests.rls_guc_check
"""
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import backend.config as cfg
from backend.models import rls  # noqa: F401  registers the after_begin listener
from backend.models.rls import set_org_context, reset_org_context

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def _guc(session):
    # missing_ok=true -> NULL if never set this transaction.
    return await session.scalar(text("SELECT current_setting('app.org_id', true)"))


async def run():
    url = os.environ["PGURL"].replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # 1. Disabled -> no-op (unset -> NULL).
        cfg.settings.RLS_ENABLED = False
        reset_org_context()
        async with Session() as s:
            check("disabled -> app.org_id unset (NULL)", await _guc(s) is None)

        # Enable enforcement plumbing for the rest.
        cfg.settings.RLS_ENABLED = True

        # 2. Enabled, no context -> '' (fail-closed empty).
        reset_org_context()
        async with Session() as s:
            check("enabled, no context -> ''", (await _guc(s)) == "")

        # 3. With a context -> echoed.
        set_org_context("org-ALPHA")
        async with Session() as s:
            check("enabled, org set -> echoed", (await _guc(s)) == "org-ALPHA")

        # 4. Across a COMMIT the org is re-applied on the new transaction.
        set_org_context("org-BETA")
        async with Session() as s:
            first = await _guc(s)
            await s.commit()                 # ends txn; set_config(...,true) cleared
            second = await _guc(s)           # new txn -> after_begin re-applies
            check("org survives across commit (re-applied)",
                  first == "org-BETA" and second == "org-BETA")
    finally:
        cfg.settings.RLS_ENABLED = False
        reset_org_context()
        await engine.dispose()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", ", ".join(FAIL))
        raise SystemExit(1)
    print("STAGE 2 GUC PLUMBING PROVEN")


if __name__ == "__main__":
    asyncio.run(run())
