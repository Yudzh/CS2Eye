from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.services.prediction_history_service import PredictionHistoryService


router = APIRouter(prefix="/prediction-history", tags=["prediction-history"])


class CaptureRequest(BaseModel):
    match_id: int
    as_of: datetime | None = None
    retrospective: bool = False


@router.post("/snapshots")
async def capture(body: CaptureRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        row = await PredictionHistoryService(session).capture(body.match_id, as_of=body.as_of, retrospective=body.retrospective)
        await session.commit()
        return {"id": row.id, "match_id": row.match_id, "created_at": row.created_at}
    except LookupError as error:
        await session.rollback()
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await session.rollback()
        raise HTTPException(422, str(error)) from error


@router.post("/tournaments/{tournament_id}/snapshots")
async def capture_tournament(
    tournament_id: int, session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        result = await PredictionHistoryService(session).capture_tournament(tournament_id)
        await session.commit()
        return result
    except LookupError as error:
        await session.rollback()
        raise HTTPException(404, str(error)) from error


@router.get("")
async def history(
    tournament_id: int | None = None,
    match_date: date | None = None,
    status: str | None = Query(None, pattern="^(completed|future)$"),
    consensus_3_3: bool = False,
    conflict_only: bool = False,
    strong_conflicts: bool = False,
    source: str | None = Query(None, pattern="^(pre_match|retrospective)$"),
    ml_model_version: str | None = None,
    team_strength_model_version: str | None = None,
    matchup_model_version: str | None = None,
    comparison_type: str | None = Query(None, pattern="^(consensus_3_3|team_strength_dissent|matchup_dissent|ml_dissent|incomplete)$"),
    matchup_error_driver: str | None = None,
    error_result: str | None = Query(None, pattern="^(any|matchup|team_strength|ml)$"),
    ml_confidence_error: Literal[60, 70, 80] | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await PredictionHistoryService(session).history(
        tournament_id=tournament_id, match_date=match_date,
        status=status, consensus_3_3=consensus_3_3,
        conflict_only=conflict_only, strong_conflicts=strong_conflicts,
        source=source,
        ml_model_version=ml_model_version,
        team_strength_model_version=team_strength_model_version,
        matchup_model_version=matchup_model_version,
        comparison_type=comparison_type,
        matchup_error_driver=matchup_error_driver,
        error_result=error_result,
        ml_confidence_error=ml_confidence_error,
    )
    await session.commit()
    return result
