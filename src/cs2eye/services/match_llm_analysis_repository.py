from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_runtime import MatchLLMRuntimeMetadata
from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun
from cs2eye.prompts.match_analysis_v5 import PROMPT_VERSION


VALID_STATUSES = {"completed", "skipped_insufficient_data"}


def json_snapshot(value) -> dict:
    """Detach a JSON-compatible deep copy from mutable Pydantic/ORM state."""
    raw = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return json.loads(json.dumps(raw, ensure_ascii=False))


class MatchLLMAnalysisRunRepository(Protocol):
    async def create_run(self, **values) -> MatchLLMAnalysisRun: ...
    async def complete_run(self, run, response, *, skipped: bool = False) -> MatchLLMAnalysisRun: ...
    async def fail_run(self, run, error) -> MatchLLMAnalysisRun: ...
    async def get_by_id(self, run_id: int) -> MatchLLMAnalysisRun | None: ...
    async def get_latest(self, **filters) -> MatchLLMAnalysisRun | None: ...
    async def list_history(self, **filters) -> list[MatchLLMAnalysisRun]: ...


class SQLAlchemyMatchLLMAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self, *, context: MatchAnalysisContext, team_a_id: int, team_b_id: int,
        match_id: int | None, tournament_id: int | None, as_of: datetime,
        analysis_mode: str, language: str, model: str | None,
        provider: str | None = "ollama", source_run_id: int | None = None,
        explanation_plan: MatchExplanationPlanV2 | None = None,
    ) -> MatchLLMAnalysisRun:
        run = MatchLLMAnalysisRun(
            source_run_id=source_run_id, match_id=match_id,
            team_a_id=team_a_id, team_b_id=team_b_id, tournament_id=tournament_id,
            as_of=as_of, analysis_mode=analysis_mode, language=language,
            status="pending", llm_called=False,
            context_schema_version=context.schema_version,
            analysis_schema_version="match_llm_analysis.v3",
            prompt_version=PROMPT_VERSION, provider=provider, model=model,
            context_snapshot=json_snapshot(context),
            explanation_plan_schema_version=(explanation_plan.schema_version
                                             if explanation_plan else None),
            explanation_plan_snapshot=(json_snapshot(explanation_plan)
                                       if explanation_plan else None),
            analysis_snapshot=None,
            attempts=0, schema_valid=False, business_valid=False,
            grounding_valid=False, repair_attempted=False,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def complete_run(self, run, response, *, skipped=False):
        if run.status != "pending":
            raise ValueError("only pending analysis runs can be completed")
        runtime: MatchLLMRuntimeMetadata = response.runtime
        run.status = "skipped_insufficient_data" if skipped else "completed"
        run.llm_called = runtime.provider != "none"
        run.analysis_snapshot = json_snapshot(response.analysis)
        run.analysis_schema_version = response.analysis.schema_version
        run.prompt_version = runtime.prompt_version
        if response.explanation_plan is not None:
            run.explanation_plan_schema_version = response.explanation_plan.schema_version
            run.explanation_plan_snapshot = json_snapshot(response.explanation_plan)
        run.provider_response_id = runtime.provider_response_id
        run.attempts = runtime.attempts
        run.input_tokens = runtime.input_tokens
        run.output_tokens = runtime.output_tokens
        run.schema_valid = runtime.schema_valid
        run.business_valid = runtime.business_valid
        run.grounding_valid = runtime.grounding_valid
        run.repair_attempted = runtime.repair_attempted
        run.grounding_error_codes = runtime.grounding_error_codes or None
        run.completed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def fail_run(self, run, error):
        if run.status != "pending":
            raise ValueError("only pending analysis runs can fail")
        run.status = "failed"
        run.llm_called = error.code != "llm_not_configured"
        run.analysis_snapshot = None
        run.attempts = error.attempts
        run.input_tokens = error.input_tokens
        run.output_tokens = error.output_tokens
        run.schema_valid = error.schema_valid
        run.business_valid = error.business_valid
        run.grounding_valid = error.grounding_valid
        run.repair_attempted = error.repair_attempted
        run.error_code = error.code
        run.error_message = str(error)[:1000]
        run.validation_error_codes = list(error.validation_error_codes) or None
        run.grounding_error_codes = [item.code for item in error.grounding_errors] or None
        run.completed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_by_id(self, run_id):
        return await self.session.get(MatchLLMAnalysisRun, run_id)

    async def get_latest(
        self, *, team_a_id: int, team_b_id: int, match_id: int | None = None,
        analysis_mode: str = "pre_match",
    ):
        query = select(MatchLLMAnalysisRun).where(
            MatchLLMAnalysisRun.status.in_(VALID_STATUSES),
            MatchLLMAnalysisRun.team_a_id == team_a_id,
            MatchLLMAnalysisRun.team_b_id == team_b_id,
        )
        if match_id is not None:
            query = query.where(MatchLLMAnalysisRun.match_id == match_id)
        else:
            query = query.where(
                MatchLLMAnalysisRun.match_id.is_(None),
                MatchLLMAnalysisRun.analysis_mode == analysis_mode,
            )
        query = query.order_by(
            MatchLLMAnalysisRun.created_at.desc(), MatchLLMAnalysisRun.id.desc(),
        ).limit(1)
        return (await self.session.scalars(query)).first()

    async def list_history(
        self, *, match_id=None, team_a_id=None, team_b_id=None, status=None,
        limit=50, offset=0,
    ):
        query = select(MatchLLMAnalysisRun)
        for column, value in (
            (MatchLLMAnalysisRun.match_id, match_id),
            (MatchLLMAnalysisRun.team_a_id, team_a_id),
            (MatchLLMAnalysisRun.team_b_id, team_b_id),
            (MatchLLMAnalysisRun.status, status),
        ):
            if value is not None:
                query = query.where(column == value)
        query = query.order_by(
            MatchLLMAnalysisRun.created_at.desc(), MatchLLMAnalysisRun.id.desc(),
        ).offset(offset).limit(limit)
        return list((await self.session.scalars(query)).all())
