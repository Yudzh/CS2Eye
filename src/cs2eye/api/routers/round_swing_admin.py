from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.services.round_swing_service import recalculate_all_swing, recalculate_demo_swing, refresh_swing_normalization, round_swing_audit, train_round_win_model

router = APIRouter(prefix="/admin/round-swing", tags=["admin", "round-swing"])

@router.post("/train")
async def train(session: AsyncSession = Depends(get_db_session)):
    report = await train_round_win_model(session); await session.commit(); return report

@router.post("/recalculate/{demo_file_id}")
async def recalculate(demo_file_id: int, session: AsyncSession = Depends(get_db_session)):
    status = await recalculate_demo_swing(session, demo_file_id); await session.commit()
    return {"demo_file_id":demo_file_id,"round_swing_status":status}

@router.post("/recalculate-all")
async def recalculate_all(session: AsyncSession = Depends(get_db_session)):
    result = await recalculate_all_swing(session); await session.commit(); return result

@router.post("/refresh-normalization")
async def refresh_normalization(session: AsyncSession = Depends(get_db_session)):
    result=await refresh_swing_normalization(session);await session.commit();return result

@router.post("/audit")
async def audit(session: AsyncSession = Depends(get_db_session)):
    result=await round_swing_audit(session);await session.commit();return result
