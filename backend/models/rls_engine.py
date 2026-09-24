"""
RLS Backstop — Stage 3 (DRAFT). Dual-engine scaffolding. DORMANT.

Under RLS, ordinary org-scoped request handlers connect as the restricted `app_rls`
role (RLS-enforced; scoped to app.org_id, which Stage 2 already stamps per request).
But several legitimate paths are cross-org and would fail-closed to 0 rows if forced
through RLS, so they use a PRIVILEGED engine (today's superuser connection) and set
app.org_id explicitly only where they must scope:

  - Auth bootstrap: login / refresh / signup / password-reset look up a user before
    any org is known.
  - Public share links: GET /reports/{id}/share/{token} reads a report across orgs.
  - Workers: the job-queue poll is inherently cross-org; a worker scopes per job via
    set_org_context(job.organization_id) before it touches tenant data.

This module exposes both engines + FastAPI DB dependencies. It is DORMANT until BOTH
`RLS_ENABLED` is true AND `DATABASE_URL_RESTRICTED` (the app_rls DSN) is set: with
either unset, the restricted dependency yields the existing (privileged) session, so
importing or merging this file changes NOTHING. Wiring the routers to the right
dependency is done during DB-branch validation only — see
docs/security/rls-stage3-draft.md.
"""
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from backend.config import settings
from backend.models.base import engine as privileged_engine, AsyncSessionLocal as PrivilegedSessionLocal

# Active only when explicitly turned on AND a restricted DSN exists. Both default off,
# so this whole file is a no-op in prod and in CI today.
_RLS_ACTIVE = bool(getattr(settings, "RLS_ENABLED", False)) and bool(getattr(settings, "DATABASE_URL_RESTRICTED", ""))

if _RLS_ACTIVE:
    restricted_engine = create_async_engine(
        settings.DATABASE_URL_RESTRICTED,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )
    RestrictedSessionLocal = async_sessionmaker(restricted_engine, class_=AsyncSession, expire_on_commit=False)
else:
    # Dormant fallback: the restricted session IS the privileged one until Stage 3 is
    # validated and turned on. Nothing behaves differently.
    restricted_engine = privileged_engine
    RestrictedSessionLocal = PrivilegedSessionLocal


async def get_db_restricted() -> AsyncIterator[AsyncSession]:
    """Org-scoped request handlers. The restricted (app_rls) engine when RLS is active;
    the existing engine otherwise. At validation time, org-scoped routers swap their
    Depends(get_db) for this."""
    async with RestrictedSessionLocal() as session:
        yield session


async def get_db_privileged() -> AsyncIterator[AsyncSession]:
    """Cross-org / bootstrap paths (auth bootstrap, public share links, worker queue
    poll). ALWAYS the privileged engine, which bypasses RLS. These paths set
    app.org_id explicitly (via set_org_context) wherever they legitimately scope to a
    single org."""
    async with PrivilegedSessionLocal() as session:
        yield session
