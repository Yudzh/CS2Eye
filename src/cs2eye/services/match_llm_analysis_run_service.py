from copy import deepcopy
from datetime import datetime

from pydantic import ValidationError

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.api.schemas.match_llm_runtime import (
    MatchLLMAnalysisResponse,
    MatchLLMHistoryItem,
    MatchLLMRuntimeMetadata,
    MatchLLMStoredAnalysisResponse,
)
from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun
from cs2eye.services.match_llm_analysis_repository import MatchLLMAnalysisRunRepository
from cs2eye.services.match_llm_analysis_service import MatchLLMAnalysisService, MatchLLMServiceError


class MatchLLMAnalysisRunService:
    """Persist lifecycle around the DB-independent LLM analysis pipeline."""

    def __init__(self, analysis_service: MatchLLMAnalysisService, repository: MatchLLMAnalysisRunRepository):
        self.analysis_service = analysis_service
        self.repository = repository

    async def generate(
        self, team_a_id: int, team_b_id: int, *, as_of: datetime,
        match_id: int | None = None, tournament_id: int | None = None,
        match_format: str | None = None,
        analysis_mode: str = "pre_match", language: str = "ru",
        source_run_id: int | None = None,
    ) -> MatchLLMStoredAnalysisResponse:
        context = await self.analysis_service.builder.build(
            team_a_id, team_b_id, as_of=as_of, match_id=match_id,
            tournament_id=tournament_id, match_format=match_format,
            analysis_mode=analysis_mode,
        )
        return await self.generate_context(
            context, team_a_id=team_a_id, team_b_id=team_b_id, as_of=as_of,
            match_id=match_id, tournament_id=tournament_id,
            analysis_mode=analysis_mode, language=language, source_run_id=source_run_id,
        )

    async def generate_context(
        self, context: MatchAnalysisContext, *, team_a_id: int, team_b_id: int,
        as_of: datetime, match_id: int | None, tournament_id: int | None,
        analysis_mode: str, language: str, source_run_id: int | None = None,
        explanation_plan: MatchExplanationPlanV2 | None = None,
    ) -> MatchLLMStoredAnalysisResponse:
        plan = explanation_plan or self.analysis_service.explanation_builder.build(context)
        run = await self.repository.create_run(
            context=context, team_a_id=team_a_id, team_b_id=team_b_id,
            match_id=match_id, tournament_id=tournament_id, as_of=as_of,
            analysis_mode=analysis_mode, language=language,
            model=self.analysis_service.model, provider="ollama",
            source_run_id=source_run_id, explanation_plan=plan,
        )
        try:
            response = await self.analysis_service.explain_context(context, plan)
        except MatchLLMServiceError as error:
            await self.repository.fail_run(run, error)
            error.analysis_run_id = run.id
            raise
        run = await self.repository.complete_run(
            run, response,
            skipped=response.runtime.provider == "none" and response.runtime.attempts == 0,
        )
        return self.detail(run)

    async def regenerate(
        self, source_run_id: int, *, reuse_context: bool = True,
        reuse_explanation_plan: bool = False, as_of: datetime | None = None,
    ) -> MatchLLMStoredAnalysisResponse:
        source = await self.repository.get_by_id(source_run_id)
        if source is None:
            raise LookupError("LLM analysis run not found")
        if reuse_explanation_plan:
            if source.explanation_plan_snapshot is None:
                raise ValueError("Source run has no stored explanation plan")
            if source.explanation_plan_schema_version != "match_explanation_plan.v2":
                raise ValueError(
                    "Source run's explanation plan uses a retired schema version "
                    f"({source.explanation_plan_schema_version}) and can no longer be reused",
                )
            context = MatchAnalysisContext.model_validate(source.context_snapshot)
            plan = MatchExplanationPlanV2.model_validate(_compatible_v2_plan_snapshot(
                source.explanation_plan_snapshot, source.context_snapshot,
            ))
            return await self.generate_context(
                context, team_a_id=source.team_a_id, team_b_id=source.team_b_id,
                as_of=source.as_of, match_id=source.match_id,
                tournament_id=source.tournament_id, analysis_mode=source.analysis_mode,
                language=source.language, source_run_id=source.id,
                explanation_plan=plan,
            )
        if reuse_context:
            context = MatchAnalysisContext.model_validate(source.context_snapshot)
            return await self.generate_context(
                context, team_a_id=source.team_a_id, team_b_id=source.team_b_id,
                as_of=source.as_of, match_id=source.match_id,
                tournament_id=source.tournament_id, analysis_mode=source.analysis_mode,
                language=source.language, source_run_id=source.id,
            )
        if as_of is None:
            raise ValueError("as_of is required when reuse_context=false")
        return await self.generate(
            source.team_a_id, source.team_b_id, as_of=as_of,
            match_id=source.match_id, tournament_id=source.tournament_id,
            analysis_mode=source.analysis_mode, language=source.language,
            source_run_id=source.id,
        )

    @staticmethod
    def detail(run: MatchLLMAnalysisRun) -> MatchLLMStoredAnalysisResponse:
        runtime = MatchLLMRuntimeMetadata(
            provider="none" if not run.llm_called else (run.provider or "ollama"),
            model=run.model or "none",
            prompt_version=run.prompt_version,
            attempts=run.attempts,
            input_tokens=run.input_tokens, output_tokens=run.output_tokens,
            provider_response_id=run.provider_response_id,
            schema_valid=run.schema_valid, business_valid=run.business_valid,
            grounding_valid=run.grounding_valid,
            repair_attempted=run.repair_attempted,
            grounding_error_codes=run.grounding_error_codes or [],
        )
        plan = None
        if (
            run.explanation_plan_snapshot is not None
            and run.explanation_plan_schema_version == "match_explanation_plan.v2"
        ):
            try:
                plan = MatchExplanationPlanV2.model_validate(_compatible_v2_plan_snapshot(
                    run.explanation_plan_snapshot, run.context_snapshot,
                ))
            except ValidationError:
                plan = None
        analysis = None
        if run.analysis_snapshot is not None:
            try:
                analysis = (
                    MatchLLMAnalysisV3.model_validate(run.analysis_snapshot)
                    if run.analysis_schema_version == "match_llm_analysis.v3"
                    else MatchLLMAnalysis.model_validate(run.analysis_snapshot)
                )
            except ValidationError:
                analysis = None
        return MatchLLMStoredAnalysisResponse(
            analysis_run_id=run.id, source_run_id=run.source_run_id,
            status=run.status,
            context=MatchAnalysisContext.model_validate(run.context_snapshot),
            explanation_plan=plan,
            analysis=analysis,
            runtime=runtime, error_code=run.error_code,
            error_message=run.error_message,
            validation_error_codes=run.validation_error_codes or [],
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    def history_item(run: MatchLLMAnalysisRun) -> MatchLLMHistoryItem:
        analysis = run.analysis_snapshot or {}
        plan = run.explanation_plan_snapshot or {}
        conclusion = (plan.get("conclusion") or {}) if plan else (analysis.get("conclusion") or {})
        return MatchLLMHistoryItem(
            id=run.id, source_run_id=run.source_run_id, created_at=run.created_at,
            status=run.status, provider=run.provider, model=run.model,
            prompt_version=run.prompt_version, as_of=run.as_of,
            analysis_status=plan.get("status") if plan else analysis.get("analysis_status"),
            favored_team=conclusion.get("favored_team"),
            confidence=conclusion.get("confidence"),
        )


def _compatible_v2_plan_snapshot(
    snapshot: dict, context_snapshot: dict,
) -> dict:
    """Hydrate display names absent from early v2 snapshots.

    The first persisted v2 plans stored stable team sides but not their display
    names. Adding the names at read time keeps those immutable DB snapshots
    readable without changing analytics or regenerating an analysis.
    """
    plan = deepcopy(snapshot)
    teams = context_snapshot.get("teams") or {}
    names = {
        side: str((teams.get(side) or {}).get("name") or side)
        for side in ("team_a", "team_b")
    }

    def add_name(item: dict, side_key: str, name_key: str) -> None:
        if name_key not in item:
            side = item.get(side_key)
            item[name_key] = names.get(side) if side in names else None

    conclusion = plan.get("conclusion") or {}
    add_name(conclusion, "favored_team", "favored_team_name")
    comparison = ((plan.get("form") or {}).get("comparison") or {})
    add_name(comparison, "favored_team", "favored_team_name")
    for edge in (plan.get("maps") or {}).get("key_map_edges") or []:
        add_name(edge, "favored_team", "favored_team_name")
        for reason in edge.get("reasons") or []:
            add_name(reason, "side", "side_name")
    for signal in (plan.get("teamplay") or {}).get("signals") or []:
        add_name(signal, "side", "side_name")
    return plan
