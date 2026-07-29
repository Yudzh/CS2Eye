from fastapi import APIRouter

from cs2eye.api.routers.bo3_admin import router as bo3_admin_router
from cs2eye.api.routers.health import router as health_router
from cs2eye.api.routers.teams import router as teams_router
from cs2eye.api.routers.players import router as players_router
from cs2eye.api.routers.demos import router as demos_router


api_router = APIRouter(
    prefix="/api/v1",
)
api_router.include_router(
    health_router,
)
api_router.include_router(
    teams_router,
)
api_router.include_router(
    players_router,
)
api_router.include_router(
    bo3_admin_router,
)
api_router.include_router(
    demos_router,
)
