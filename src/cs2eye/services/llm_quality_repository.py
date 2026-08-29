from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.llm_quality import (
    LLMQualityConfiguration, LLMQualityReviewCreate, LLMQualityReviewResponse,
    LLMQualityRunResult,
)
from cs2eye.models.llm_quality import LLMQualityReview, LLMQualityRun


class LLMQualityRepository(Protocol):
    async def save_run(self, result: LLMQualityRunResult) -> LLMQualityRunResult: ...
    async def list_runs(self, dataset_version: str, configuration: LLMQualityConfiguration
                        ) -> list[LLMQualityRunResult]: ...
    async def add_review(self, run_id: int, review: LLMQualityReviewCreate
                         ) -> LLMQualityReviewResponse: ...
    async def manual_counts(self, run_ids: list[int]) -> tuple[int, int]: ...


class SQLAlchemyLLMQualityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_run(self, result):
        row = LLMQualityRun(
            case_id=result.case_id, dataset_version=result.dataset_version,
            provider=result.configuration.provider, model=result.configuration.model,
            prompt_version=result.configuration.prompt_version,
            reasoning_config=result.configuration.reasoning,
            explanation_plan_snapshot=result.explanation_plan_snapshot.model_dump(mode="json"),
            llm_output_snapshot=(result.llm_output_snapshot.model_dump(mode="json")
                                 if result.llm_output_snapshot else None),
            deterministic_metrics=(result.deterministic_metrics.model_dump(mode="json")
                                   if result.deterministic_metrics else None),
            quality_score=result.quality_score, status=result.status,
            error_code=result.error_code,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return result.model_copy(update={"id": row.id, "created_at": row.created_at})

    async def list_runs(self, dataset_version, configuration):
        rows = (await self.session.scalars(select(LLMQualityRun).where(
            LLMQualityRun.dataset_version == dataset_version,
            LLMQualityRun.provider == configuration.provider,
            LLMQualityRun.model == configuration.model,
            LLMQualityRun.prompt_version == configuration.prompt_version,
        ).order_by(LLMQualityRun.id))).all()
        matching = [row for row in rows if row.reasoning_config == configuration.reasoning]
        latest_by_case = {row.case_id: row for row in matching}
        return [self._result(row) for row in latest_by_case.values()]

    async def add_review(self, run_id, review):
        row = LLMQualityReview(quality_run_id=run_id, **review.model_dump())
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return LLMQualityReviewResponse(id=row.id, quality_run_id=run_id,
                                        created_at=row.created_at, **review.model_dump())

    async def manual_counts(self, run_ids):
        if not run_ids:
            return 0, 0
        rows = (await self.session.scalars(select(LLMQualityReview).where(
            LLMQualityReview.quality_run_id.in_(run_ids)
        ))).all()
        return sum(row.rating == "good" for row in rows), len(rows)

    @staticmethod
    def _result(row):
        from cs2eye.api.schemas.llm_quality import LLMQualityMetrics
        from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
        from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
        return LLMQualityRunResult(
            id=row.id, case_id=row.case_id, dataset_version=row.dataset_version,
            configuration=LLMQualityConfiguration(
                provider=row.provider, model=row.model, prompt_version=row.prompt_version,
                reasoning=row.reasoning_config,
            ),
            explanation_plan_snapshot=MatchExplanationPlan.model_validate(
                row.explanation_plan_snapshot),
            llm_output_snapshot=(MatchLLMAnalysisV2.model_validate(row.llm_output_snapshot)
                                 if row.llm_output_snapshot else None),
            deterministic_metrics=(LLMQualityMetrics.model_validate(row.deterministic_metrics)
                                   if row.deterministic_metrics else None),
            quality_score=row.quality_score, status=row.status, error_code=row.error_code,
            created_at=row.created_at,
        )
