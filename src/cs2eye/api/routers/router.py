from fastapi import APIRouter

from cs2eye.api.routers.bo3_admin import router as bo3_admin_router
from cs2eye.api.routers.health import router as health_router
from cs2eye.api.routers.teams import router as teams_router
from cs2eye.api.routers.players import router as players_router
from cs2eye.api.routers.demos import router as demos_router
from cs2eye.api.routers.meta import router as meta_router
from cs2eye.api.routers.analysis import router as analysis_router
from cs2eye.api.routers.matches import router as matches_router
from cs2eye.api.routers.round_swing_admin import router as round_swing_admin_router
from cs2eye.api.routers.tournaments import router as tournaments_router
from cs2eye.api.routers.analyst_factors import router as analyst_factors_router
from cs2eye.api.routers.ml_models import router as ml_models_router


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
api_router.include_router(meta_router)
api_router.include_router(analysis_router)
api_router.include_router(matches_router)
api_router.include_router(tournaments_router)
api_router.include_router(round_swing_admin_router)
api_router.include_router(analyst_factors_router)
api_router.include_router(ml_models_router)
