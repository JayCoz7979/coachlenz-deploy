from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.config import settings

# Pool sizing applies to Postgres only. SQLite (the test harness) uses a pool that
# rejects pool_size/max_overflow, so we pass those just for real databases.
_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )
engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Register the RLS org-context listener (dormant unless settings.RLS_ENABLED and
# the dialect is postgresql). Import for its side effect of attaching the
# after_begin hook to the Session class. See backend/models/rls.py.
from backend.models import rls  # noqa: E402,F401
