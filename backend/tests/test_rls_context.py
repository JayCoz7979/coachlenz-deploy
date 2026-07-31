"""
Unit tests for the RLS org-context ContextVar (backend/models/rls.py). These are
pure (no DB): they cover the set/get/reset helpers and, critically, that the
context does NOT leak across concurrent asyncio tasks — each request/job must see
only its own org. The listener's actual GUC stamping is proven against real
Postgres in backend/tests/rls_guc_check.py (SQLite/CI cannot run RLS).
"""
import asyncio

import pytest

from backend.models.rls import set_org_context, get_org_context, reset_org_context


@pytest.mark.unit
def test_set_get_reset():
    reset_org_context()
    assert get_org_context() is None
    set_org_context("org-123")
    assert get_org_context() == "org-123"
    reset_org_context()
    assert get_org_context() is None


@pytest.mark.unit
def test_falsey_org_is_none():
    set_org_context("")
    assert get_org_context() is None
    set_org_context(None)
    assert get_org_context() is None


@pytest.mark.unit
def test_uuid_is_stringified():
    import uuid
    u = uuid.uuid4()
    set_org_context(u)
    assert get_org_context() == str(u)
    reset_org_context()


@pytest.mark.unit
def test_no_cross_task_leak():
    """Two concurrent tasks set different orgs; neither may see the other's.
    ContextVars are copied per task, which is exactly the isolation RLS needs so a
    burst of concurrent requests can't cross-stamp each other's org."""
    async def worker(org, hold):
        set_org_context(org)
        await asyncio.sleep(hold)          # yield so the tasks interleave
        return get_org_context()

    async def main():
        return await asyncio.gather(
            worker("org-A", 0.02),
            worker("org-B", 0.01),
            worker("org-C", 0.015),
        )

    a, b, c = asyncio.run(main())
    assert (a, b, c) == ("org-A", "org-B", "org-C")
