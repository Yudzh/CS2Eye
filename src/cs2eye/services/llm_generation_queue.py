"""Serialize generation across requests and PostgreSQL API workers."""
import asyncio
from contextlib import asynccontextmanager
from weakref import WeakKeyDictionary

from sqlalchemy import text

from cs2eye.db.session import engine

_locks = WeakKeyDictionary()
# Stable application-specific PostgreSQL advisory lock key.
_LOCK_KEY = 4849332001


@asynccontextmanager
async def generation_slot(database_engine=engine):
    loop = asyncio.get_running_loop()
    lock = _locks.setdefault(loop, asyncio.Lock())
    # Waiting is bounded independently of the provider's generation timeout.
    async with asyncio.timeout(120):
        await lock.acquire()
    try:
        if database_engine.dialect.name == "postgresql":
            async with database_engine.begin() as connection:
                async with asyncio.timeout(120):
                    while not await connection.scalar(
                        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _LOCK_KEY},
                    ):
                        await asyncio.sleep(0.25)
                yield
        else:
            yield
    finally:
        lock.release()
