import asyncio
from types import SimpleNamespace

import pytest

from cs2eye.services.llm_generation_queue import generation_slot


SQLITE = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))


async def test_generations_wait_and_release_after_failure():
    entered = asyncio.Event()
    release = asyncio.Event()
    order = []

    async def first():
        with pytest.raises(ValueError):
            async with generation_slot(SQLITE):
                order.append("first")
                entered.set()
                await release.wait()
                raise ValueError("provider failed")

    async def second():
        await entered.wait()
        async with generation_slot(SQLITE):
            order.append("second")

    one = asyncio.create_task(first())
    two = asyncio.create_task(second())
    await entered.wait()
    await asyncio.sleep(0)
    assert order == ["first"]
    release.set()
    await asyncio.gather(one, two)
    assert order == ["first", "second"]


async def test_cancelled_generation_releases_slot():
    entered = asyncio.Event()

    async def generate():
        async with generation_slot(SQLITE):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(generate())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(1):
        async with generation_slot(SQLITE):
            pass


async def test_postgres_lock_is_held_until_generation_finishes():
    from contextlib import asynccontextmanager

    events = []

    class Connection:
        async def scalar(self, query, params):
            assert "pg_try_advisory_xact_lock" in str(query)
            events.append("locked")
            return True

    @asynccontextmanager
    async def begin():
        try:
            yield Connection()
        finally:
            events.append("released")

    database = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), begin=begin)
    with pytest.raises(ValueError):
        async with generation_slot(database):
            events.append("generation")
            raise ValueError("failed")
    assert events == ["locked", "generation", "released"]
