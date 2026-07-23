from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.core.config import settings
from cs2eye.db.session import get_db_session


router = APIRouter(
    prefix="/health",
    tags=["health"],
)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class ReadinessResponse(HealthResponse):
    database: Literal["ok"]


@router.get(
    "/live",
    response_model=HealthResponse,
)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
)
async def readiness(
    session: AsyncSession = Depends(
        get_db_session,
    ),
) -> ReadinessResponse:
    await session.execute(
        text("SELECT 1"),
    )

    return ReadinessResponse(
        status="ok",
        service=settings.app_name,
        database="ok",
    )
