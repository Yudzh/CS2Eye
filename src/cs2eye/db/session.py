from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cs2eye.core.config import settings


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # Docker/VPN restarts can leave asyncpg connections in the pool after
    # PostgreSQL has already closed them. Validate a connection when it is
    # checked out so requests transparently receive a fresh one instead of an
    # asyncpg "connection is closed" InterfaceError.
    pool_pre_ping=True,
    pool_recycle=300,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> (
    AsyncGenerator[AsyncSession, None]
):
    async with AsyncSessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()
