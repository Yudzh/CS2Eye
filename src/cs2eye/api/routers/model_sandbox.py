from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.services.model_sandbox_service import ModelSandboxService

router=APIRouter(prefix="/admin/model-sandbox",tags=["model-sandbox"])

class StrictBody(BaseModel):model_config=ConfigDict(extra="forbid")
class MatchupPreviewBody(StrictBody):match_id:int;config:dict[str,Any]
class MatchupBacktestBody(StrictBody):config:dict[str,Any];limit:int=Field(120,ge=1,le=500)
class MLTrainBody(StrictBody):enabled_features:list[str]

@router.get("")
async def bootstrap(session:AsyncSession=Depends(get_db_session)):return await ModelSandboxService(session).bootstrap()

@router.post("/matchup/preview")
async def preview(body:MatchupPreviewBody,session:AsyncSession=Depends(get_db_session)):
    try:return await ModelSandboxService(session).preview(body.match_id,body.config)
    except ValueError as error:raise HTTPException(422,str(error)) from error

@router.post("/matchup/backtest")
async def backtest(body:MatchupBacktestBody,session:AsyncSession=Depends(get_db_session)):
    try:return await ModelSandboxService(session).backtest(body.config,body.limit)
    except ValueError as error:raise HTTPException(422,str(error)) from error

@router.post("/ml/train")
async def train(body:MLTrainBody,session:AsyncSession=Depends(get_db_session)):
    try:
        result=await ModelSandboxService(session).train_ml(body.enabled_features);await session.commit();return result
    except ValueError as error:
        await session.rollback();raise HTTPException(422,str(error)) from error
