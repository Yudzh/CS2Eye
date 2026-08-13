from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.services.round_swing_service import recalculate_demo_swing, train_round_win_model

router = APIRouter(prefix="/admin/round-swing", tags=["admin", "round-swing"])

@router.post("/train")
async def train(session: AsyncSession = Depends(get_db_session)):
    report = await train_round_win_model(session); await session.commit(); return report

@router.post("/recalculate/{demo_file_id}")
async def recalculate(demo_file_id: int, session: AsyncSession = Depends(get_db_session)):
    status = await recalculate_demo_swing(session, demo_file_id); await session.commit()
    return {"demo_file_id":demo_file_id,"round_swing_status":status}
