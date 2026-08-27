from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.services.win_probability_service import activate_win_probability, win_probability_status


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
