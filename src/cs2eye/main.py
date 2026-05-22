from fastapi import FastAPI

from cs2eye.core.config import settings
from cs2eye.api.routers.health import router as health_router
from cs2eye.api.routers.router import api_router as main_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(main_router)

    return app

app = create_app()

