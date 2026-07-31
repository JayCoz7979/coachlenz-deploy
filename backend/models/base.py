from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
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
