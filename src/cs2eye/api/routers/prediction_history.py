from datetime import date, datetime

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
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await PredictionHistoryService(session).history(
        tournament_id=tournament_id, match_date=match_date,
        status=status, consensus_3_3=consensus_3_3,
        conflict_only=conflict_only, strong_conflicts=strong_conflicts,
    )
    await session.commit()
    return result
