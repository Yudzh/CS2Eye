from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.llm_quality import (
    LLMQualityDataset, LLMQualityReviewCreate, LLMQualityReviewResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.llm_quality.dataset_v2 import DATASET_V2
from cs2eye.services.llm_quality_repository import SQLAlchemyLLMQualityRepository


router = APIRouter(prefix="/admin/llm-quality", tags=["llm-quality"])


@router.get("/dataset", response_model=LLMQualityDataset)
async def quality_dataset():
    return DATASET_V2


@router.post("/runs/{run_id}/reviews", response_model=LLMQualityReviewResponse)
async def create_quality_review(
    run_id: int, body: LLMQualityReviewCreate,
    session: AsyncSession = Depends(get_db_session),
):
    result = await SQLAlchemyLLMQualityRepository(session).add_review(run_id, body)
    await session.commit()
    return result

