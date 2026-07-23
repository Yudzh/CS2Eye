from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from cs2eye.api.routers.router import api_router
from cs2eye.core.config import settings
from cs2eye.db.session import dispose_engine


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    del app
    yield
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
