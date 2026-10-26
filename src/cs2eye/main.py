from contextlib import asynccontextmanager, suppress
import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI

from cs2eye.api.routers.router import api_router
from cs2eye.core.config import settings
from cs2eye.db.session import dispose_engine, AsyncSessionLocal
from cs2eye.services.tournament_lineup_monitor import TournamentLineupMonitor
from cs2eye.services.match_result_sync_service import result_sync_loop
from cs2eye.services.prediction_capture_monitor import prediction_capture_loop


async def roster_check_loop():
    while True:
        try:
            async with AsyncSessionLocal() as session:
                from cs2eye.services.pandascore_roster_service import PandaScoreRosterService
                if settings.pandascore_api_token.get_secret_value():
                    await PandaScoreRosterService(session).refresh_due_main()
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
    result_task = asyncio.create_task(result_sync_loop())
    try:
        yield
    finally:
        result_task.cancel()
        with suppress(asyncio.CancelledError):
            await result_task
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
