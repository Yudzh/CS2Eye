from fastapi import APIRouter

from cs2eye.core.config import settings

router = APIRouter(tags=["health"])

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
    }