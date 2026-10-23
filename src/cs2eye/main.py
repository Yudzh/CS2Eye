from contextlib import asynccontextmanager, suppress
import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI

from cs2eye.api.routers.router import api_router
from cs2eye.core.config import settings
from cs2eye.db.session import dispose_engine, AsyncSessionLocal
from cs2eye.services.tournament_lineup_monitor import TournamentLineupMonitor
from cs2eye.services.prediction_capture_monitor import prediction_capture_loop


async def roster_check_loop():
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await TournamentLineupMonitor(session).check_due()
        except Exception:
            logging.getLogger(__name__).exception("Tournament roster check failed")
        await asyncio.sleep(900)



@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    del app
    task = asyncio.create_task(roster_check_loop())
    prediction_task = asyncio.create_task(prediction_capture_loop())
    try:
        yield
    finally:
        prediction_task.cancel()
        with suppress(asyncio.CancelledError):
            await prediction_task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)

    return app


app = create_app()
