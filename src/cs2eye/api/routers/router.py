from fastapi import APIRouter

from cs2eye.api.routers.demos import router as demos_router


api_router = APIRouter(prefix="/api/v1")

api_router.include_router(demos_router)
