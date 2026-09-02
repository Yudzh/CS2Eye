from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.services.win_probability_service import activate_win_probability, win_probability_status
from cs2eye.services.win_probability_feature_diagnostics_service import WinProbabilityFeatureDiagnosticsService


router = APIRouter(prefix="/ml/models", tags=["ml-models"])


class ModelActivationRequest(BaseModel):
    force: bool = False


@router.get("")
async def models(session: AsyncSession = Depends(get_db_session)) -> dict:
    return await win_probability_status(session)


@router.post("/{model_id}/activate")
async def activate_model(model_id: int, body: ModelActivationRequest,
                         session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        result = await activate_win_probability(session, model_id, body.force)
        await session.commit()
        return result
    except ValueError as error:
        await session.rollback()
        status = 404 if "not found" in str(error).lower() else 409
        raise HTTPException(status, str(error)) from error


@router.post("/feature-diagnostics/run")
async def run_feature_diagnostics(session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        result=await WinProbabilityFeatureDiagnosticsService(session).run()
        await session.commit()
        return result
    except ValueError as error:
        await session.rollback()
        raise HTTPException(409,str(error)) from error


@router.get("/feature-diagnostics/latest")
async def latest_feature_diagnostics(session: AsyncSession = Depends(get_db_session)) -> dict:
    result=await WinProbabilityFeatureDiagnosticsService(session).latest()
    if result is None:raise HTTPException(404,"No ML feature diagnostic run exists.")
    return result
