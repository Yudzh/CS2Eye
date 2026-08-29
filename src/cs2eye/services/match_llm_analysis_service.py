import logging
from time import perf_counter
from typing import Literal

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.api.schemas.match_llm_analysis import AnalysisContradiction
from cs2eye.api.schemas.match_llm_runtime import (
    MatchLLMAnalysisResponse,
    MatchLLMRuntimeMetadata,
)
from cs2eye.prompts.match_analysis_v2 import PROMPT_VERSION
from cs2eye.prompts.match_analysis_v3 import PROMPT_VERSION as PROMPT_VERSION_V3
from cs2eye.services.deterministic_match_explanation_builder import (
    DeterministicMatchExplanationBuilder,
)
from cs2eye.services.match_explanation_assembler import assemble_match_explanation
from cs2eye.services.match_llm_analysis_v2_validator import (
    MatchLLMAnalysisV2Validator, MatchLLMV2ValidationError,
)
from cs2eye.services.match_analysis_context_builder import MatchAnalysisContextBuilder
from cs2eye.services.match_llm_analysis_validator import (
    MatchLLMAnalysisValidationError,
    MatchLLMAnalysisValidator,
)
from cs2eye.services.match_llm_grounding_validator import MatchLLMGroundingValidator
from cs2eye.services.ollama_match_analysis_client import (
    MatchAnalysisInvalidResponseError,
    MatchAnalysisProvider,
    MatchAnalysisProviderError,
    MatchAnalysisProviderResult,
    MatchAnalysisProviderTimeoutError,
)


logger = logging.getLogger(__name__)


class MatchLLMServiceError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, grounding_errors=(), attempts: int = 0,
        input_tokens: int | None = None, output_tokens: int | None = None,
        schema_valid: bool = False, business_valid: bool = False,
        grounding_valid: bool = False, repair_attempted: bool = False,
        validation_errors: tuple[str, ...] = (),
        validation_error_codes: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.grounding_errors = tuple(grounding_errors)
        self.attempts = attempts
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.schema_valid = schema_valid
        self.business_valid = business_valid
        self.grounding_valid = grounding_valid
        self.repair_attempted = repair_attempted
        self.validation_errors = validation_errors
        self.validation_error_codes = validation_error_codes
        super().__init__(message)


class MatchLLMAnalysisService:
    MAX_ATTEMPTS = 2

    def __init__(
        self,
        builder: MatchAnalysisContextBuilder,
        provider: MatchAnalysisProvider | None,
        *,
        enabled: bool,
        model: str,
        validator: MatchLLMAnalysisValidator | None = None,
        grounding_validator: MatchLLMGroundingValidator | None = None,
    ) -> None:
        self.builder = builder
        self.provider = provider
        self.enabled = enabled
        self.model = model
        self.validator = validator or MatchLLMAnalysisValidator()
        self.grounding_validator = grounding_validator or MatchLLMGroundingValidator()
        self.explanation_builder = DeterministicMatchExplanationBuilder()
        self.v2_validator = MatchLLMAnalysisV2Validator()

    async def explain_context(
        self, context: MatchAnalysisContext, plan: MatchExplanationPlan | None = None,
    ) -> MatchLLMAnalysisResponse:
        """v3 pipeline: deterministic analytics first, text-only LLM second."""
        plan = plan or self.explanation_builder.build(context)
        if plan.status == "insufficient_data":
            analysis = self._insufficient_v2(plan)
            return MatchLLMAnalysisResponse(
                context=context, explanation_plan=plan,
                rendered_analysis=assemble_match_explanation(plan, analysis),
                analysis=analysis,
                runtime=MatchLLMRuntimeMetadata(
                    provider="none", model="none", prompt_version=PROMPT_VERSION_V3,
                    attempts=0,
                ),
            )
        if not self.enabled or self.provider is None:
            raise MatchLLMServiceError(
                "llm_not_configured",
                "Match LLM analysis is disabled or Ollama is not configured.",
            )
        # Compatibility for third-party/legacy providers. The built-in Ollama client
        # always implements generate_plan and therefore always uses v3 for new runs.
        if not hasattr(self.provider, "generate_plan"):
            legacy = await self.analyze_context(context)
            return legacy.model_copy(update={"explanation_plan": plan})
        started = perf_counter()
        input_tokens = output_tokens = 0
        known = False
        repair_errors: tuple[str, ...] = ()
        previous = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                latest = await self.provider.generate_plan(
                    plan, repair_errors=repair_errors, previous_analysis=previous,
                )
            except MatchAnalysisProviderTimeoutError as error:
                raise MatchLLMServiceError(
                    "llm_timeout", str(error), attempts=attempt,
                    input_tokens=input_tokens or None, output_tokens=output_tokens or None,
                    repair_attempted=attempt > 1,
                ) from error
            except MatchAnalysisInvalidResponseError as error:
                raise MatchLLMServiceError(
                    "llm_invalid_response", str(error), attempts=attempt,
                    repair_attempted=attempt > 1,
                ) from error
            except MatchAnalysisProviderError as error:
                raise MatchLLMServiceError(
                    "llm_provider_error", str(error), attempts=attempt,
                    repair_attempted=attempt > 1,
                ) from error
            if latest.input_tokens is not None:
                input_tokens += latest.input_tokens; known = True
            if latest.output_tokens is not None:
                output_tokens += latest.output_tokens; known = True
            if not isinstance(latest.analysis, MatchLLMAnalysisV2):
                raise MatchLLMServiceError(
                    "llm_invalid_response", "Provider returned legacy analysis for v3.",
                    attempts=attempt,
                )
            try:
                self.v2_validator.validate(plan, latest.analysis)
            except MatchLLMV2ValidationError as error:
                if attempt == self.MAX_ATTEMPTS:
                    raise MatchLLMServiceError(
                        "llm_validation_failed",
                        "Ollama wording failed MatchLLMAnalysis v2 validation after repair.",
                        attempts=attempt, input_tokens=input_tokens or None,
                        output_tokens=output_tokens or None, schema_valid=True,
                        business_valid=True, repair_attempted=True,
                        validation_errors=error.errors,
                        validation_error_codes=error.codes,
                    ) from error
                repair_errors = error.errors
                previous = latest.analysis
                continue
            prompt_version = getattr(self.provider, "prompt_version", PROMPT_VERSION_V3)
            runtime = MatchLLMRuntimeMetadata(
                provider="ollama", model=self.model, prompt_version=PROMPT_VERSION_V3,
                attempts=attempt, input_tokens=input_tokens if known else None,
                output_tokens=output_tokens if known else None,
                repair_attempted=attempt > 1,
            ).model_copy(update={"prompt_version": prompt_version})
            self._log(context, attempt, started, "success", latest)
            return MatchLLMAnalysisResponse(
                context=context, explanation_plan=plan,
                rendered_analysis=assemble_match_explanation(plan, latest.analysis),
                analysis=latest.analysis,
                runtime=runtime,
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _insufficient_v2(plan: MatchExplanationPlan) -> MatchLLMAnalysisV2:
        return MatchLLMAnalysisV2(
            summary="Данных недостаточно для надёжного предматчевого объяснения.",
            advantage_texts={}, counter_argument_texts={}, contradiction_texts={},
            risk_texts={item.risk_id: "Доступные данные имеют низкую надёжность."
                        for item in plan.risks if item.severity == "high"},
            limitation_texts={item.limitation_id: "Для этого фактора недостаточно данных."
                              for item in plan.limitations if item.severity == "high"},
        )

    async def analyze(
        self,
        team_a_id: int,
        team_b_id: int,
        *,
        as_of,
        match_id: int | None = None,
        tournament_id: int | None = None,
        analysis_mode: str = "pre_match",
        language: Literal["ru", "en"] = "ru",
    ) -> MatchLLMAnalysisResponse:
        context = await self.builder.build(
            team_a_id,
            team_b_id,
            as_of=as_of,
            match_id=match_id,
            tournament_id=tournament_id,
            analysis_mode=analysis_mode,
        )
        return await self.analyze_context(context, language=language)

    async def analyze_context(
        self,
        context: MatchAnalysisContext,
        *,
        language: Literal["ru", "en"] = "ru",
    ) -> MatchLLMAnalysisResponse:
        started = perf_counter()
        if context.data_quality.overall_status == "insufficient":
            analysis = self._insufficient_analysis(context, language)
            self.validator.validate(context, analysis)
            grounding = self.grounding_validator.validate(context, analysis)
            if not grounding.valid:
                raise MatchLLMServiceError(
                    "llm_grounding_failed", "Fallback analysis failed grounding.",
                    grounding_errors=grounding.errors,
                )
            analysis = self._with_evidence_kinds(analysis, grounding.evidence_kinds)
            self._log(context, 0, started, "insufficient_data_fallback")
            return self._response(context, analysis, provider="none", attempts=0)

        if not self.enabled or self.provider is None:
            self._log(context, 0, started, "llm_not_configured")
            raise MatchLLMServiceError(
                "llm_not_configured",
                "Match LLM analysis is disabled or Ollama is not configured.",
            )

        repair_errors: tuple[str, ...] = ()
        input_tokens = 0
        output_tokens = 0
        tokens_known = False
        latest: MatchAnalysisProviderResult | None = None
        previous_analysis: MatchLLMAnalysis | None = None
        grounding_error_codes: list[str] = []
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            started = perf_counter()
            try:
                latest = await self.provider.generate(
                    context,
                    language=language,
                    repair_errors=repair_errors,
                    previous_analysis=previous_analysis,
                )
            except MatchAnalysisProviderTimeoutError as error:
                self._log(context, attempt, started, "llm_timeout")
                raise MatchLLMServiceError(
                    "llm_timeout", str(error), attempts=attempt,
                    input_tokens=input_tokens or None, output_tokens=output_tokens or None,
                    repair_attempted=attempt > 1,
                ) from error
            except MatchAnalysisInvalidResponseError as error:
                self._log(context, attempt, started, "llm_invalid_response")
                raise MatchLLMServiceError(
                    "llm_invalid_response", str(error), attempts=attempt,
                    input_tokens=input_tokens or None, output_tokens=output_tokens or None,
                    repair_attempted=attempt > 1,
                ) from error
            except MatchAnalysisProviderError as error:
                self._log(
                    context, attempt, started, f"llm_provider_error:{error.kind}",
                )
                raise MatchLLMServiceError(
                    "llm_provider_error", str(error), attempts=attempt,
                    input_tokens=input_tokens or None, output_tokens=output_tokens or None,
                    repair_attempted=attempt > 1,
                ) from error

            if latest.input_tokens is not None:
                input_tokens += latest.input_tokens
                tokens_known = True
            if latest.output_tokens is not None:
                output_tokens += latest.output_tokens
                tokens_known = True
            candidate = self._ensure_required_contradiction(
                context, latest.analysis, language,
            )
            try:
                self.validator.validate(context, candidate)
            except MatchLLMAnalysisValidationError as error:
                self._log(context, attempt, started, "validation_failed", latest)
                if attempt == self.MAX_ATTEMPTS:
                    raise MatchLLMServiceError(
                        "llm_validation_failed",
                        "Ollama response failed CS2Eye validation after repair.",
                        attempts=attempt, input_tokens=input_tokens or None,
                        output_tokens=output_tokens or None, schema_valid=True,
                        repair_attempted=attempt > 1,
                        validation_errors=error.errors,
                        validation_error_codes=error.codes,
                    ) from error
                repair_errors = error.errors
                previous_analysis = candidate
                continue

            grounding = self.grounding_validator.validate(context, candidate)
            if not grounding.valid:
                self._log(context, attempt, started, "grounding_failed", latest)
                grounding_error_codes.extend(error.code for error in grounding.errors)
                if attempt == self.MAX_ATTEMPTS:
                    candidate = self._without_ungrounded_items(
                        candidate, grounding.errors,
                    )
                    candidate = self._ensure_required_contradiction(
                        context, candidate, language,
                    )
                    candidate = self._with_safe_repair_summary(
                        context, candidate, language,
                    )
                    try:
                        self.validator.validate(context, candidate)
                    except MatchLLMAnalysisValidationError as error:
                        raise MatchLLMServiceError(
                            "llm_validation_failed",
                            "Sanitized Ollama response failed CS2Eye validation.",
                            attempts=attempt, input_tokens=input_tokens or None,
                            output_tokens=output_tokens or None, schema_valid=True,
                            repair_attempted=True, validation_errors=error.errors,
                            validation_error_codes=error.codes,
                        ) from error
                    grounding = self.grounding_validator.validate(context, candidate)
                    if not grounding.valid:
                        raise MatchLLMServiceError(
                            "llm_grounding_failed",
                            "Ollama response failed CS2Eye grounding after repair.",
                            grounding_errors=grounding.errors,
                            attempts=attempt, input_tokens=input_tokens or None,
                            output_tokens=output_tokens or None, schema_valid=True,
                            business_valid=True, repair_attempted=True,
                        )
                else:
                    repair_errors = tuple(
                        error.repair_message() for error in grounding.errors
                    )
                    previous_analysis = candidate
                    continue

            grounded_analysis = self._with_evidence_kinds(candidate, grounding.evidence_kinds)

            self._log(context, attempt, started, "success", latest)
            runtime = MatchLLMRuntimeMetadata(
                provider="ollama",
                model=self.model,
                prompt_version=PROMPT_VERSION,
                attempts=attempt,
                input_tokens=input_tokens if tokens_known else None,
                output_tokens=output_tokens if tokens_known else None,
                provider_response_id=latest.response_id,
                repair_attempted=attempt > 1,
                grounding_error_codes=grounding_error_codes,
            )
            return MatchLLMAnalysisResponse(
                context=context, analysis=grounded_analysis, runtime=runtime,
            )

        raise AssertionError("unreachable")

    def _response(
        self,
        context: MatchAnalysisContext,
        analysis: MatchLLMAnalysis,
        *,
        provider: Literal["ollama", "none"],
        attempts: int,
    ) -> MatchLLMAnalysisResponse:
        return MatchLLMAnalysisResponse(
            context=context,
            analysis=analysis,
            runtime=MatchLLMRuntimeMetadata(
                provider=provider,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                attempts=attempts,
                repair_attempted=attempts > 1,
            ),
        )

    @staticmethod
    def _insufficient_analysis(
        context: MatchAnalysisContext,
        language: Literal["ru", "en"],
    ) -> MatchLLMAnalysis:
        quality = context.data_quality
        raw_limitations = [
            *quality.limitations,
            *(
                (f"Отсутствует раздел данных: {item}" if language == "ru"
                 else f"Missing data section: {item}")
                for item in quality.missing_sections
            ),
            *quality.warnings,
        ]
        if not raw_limitations:
            raw_limitations = [
                "Контекст помечен CS2Eye как недостаточный."
                if language == "ru"
                else "The context is marked insufficient by CS2Eye."
            ]
        limitations = [
            {
                "limitation_id": f"limitation:{index}",
                "severity": "high",
                "statement": text[:1000],
                "evidence_refs": ["data_quality"],
            }
            for index, text in enumerate(raw_limitations, start=1)
        ]
        summary = (
            "Данных CS2Eye недостаточно для уверенного предматчевого анализа."
            if language == "ru"
            else "CS2Eye has insufficient data for a confident pre-match analysis."
        )
        return MatchLLMAnalysis.model_validate({
            "analysis_status": "insufficient_data",
            "conclusion": {
                "favored_team": "none",
                "advantage": "none",
                "confidence": "insufficient",
                "reasoning_basis": "ml_prediction",
            },
            "key_advantages": [],
            "counter_arguments": [],
            "contradictions": [],
            "risks": [],
            "data_limitations": limitations,
            "summary": summary,
        })

    @staticmethod
    def _with_evidence_kinds(analysis, kinds):
        updates = {}
        for collection in ("key_advantages", "counter_arguments", "risks", "data_limitations"):
            items = []
            for item in getattr(analysis, collection):
                identity = getattr(item, "claim_id", None) or getattr(item, "risk_id", None) or getattr(item, "limitation_id", None)
                items.append(item.model_copy(update={"evidence_kind": kinds.get(identity)}))
            updates[collection] = items
        return analysis.model_copy(update=updates)

    @staticmethod
    def _ensure_required_contradiction(context, analysis, language):
        """Materialize the mandatory ML/Matchup conflict as a backend fact.

        Local structured-output engines do not consistently implement JSON Schema
        uniqueness/contains constraints. The conflict direction is already computed
        deterministically from context, so it must not depend on model compliance.
        """
        if not MatchLLMAnalysisValidator._ml_matchup_conflict(context):
            return analysis
        if any(
            {"prediction", "matchup"}.issubset(item.evidence_refs)
            for item in analysis.contradictions
        ):
            return analysis
        prediction = context.prediction
        ml_side = (
            "team_a" if prediction.team_a_probability > prediction.team_b_probability
            else "team_b"
        )
        matchup_side = (
            "team_a" if context.matchup.team_a_score > context.matchup.team_b_score
            else "team_b"
        )
        ml_name = getattr(context.teams, ml_side).name or ml_side
        matchup_name = getattr(context.teams, matchup_side).name or matchup_side
        description = (
            f"ML-прогноз отдаёт преимущество {ml_name}, а детерминированный "
            f"Matchup Score склоняется к {matchup_name}."
            if language == "ru" else
            f"The ML prediction favors {ml_name}, while the deterministic "
            f"Matchup Score favors {matchup_name}."
        )
        required = AnalysisContradiction(
            contradiction_id="contradiction:ml_matchup",
            importance="high", description=description,
            evidence_refs=["prediction", "matchup"],
        )
        contradictions = [*analysis.contradictions, required]
        if len(contradictions) > 3:
            contradictions = [*analysis.contradictions[:2], required]
        return analysis.model_copy(update={"contradictions": contradictions})

    @staticmethod
    def _with_safe_repair_summary(context, analysis, language):
        """Use deterministic prose after a minimal repair response.

        The local model still supplies the structured conclusion, while backend prose
        prevents language drift, side aliases, and new qualitative facts in summary.
        """
        favorite = analysis.conclusion.favored_team
        if favorite not in {"team_a", "team_b"}:
            summary = (
                "Данных недостаточно, чтобы определить фаворита."
                if language == "ru" else
                "There is not enough data to determine a favorite."
            )
        else:
            favorite_name = getattr(context.teams, favorite).name or favorite
            if MatchLLMAnalysisValidator._ml_matchup_conflict(context):
                matchup_side = (
                    "team_a" if context.matchup.team_a_score > context.matchup.team_b_score
                    else "team_b"
                )
                matchup_name = getattr(context.teams, matchup_side).name or matchup_side
                summary = (
                    f"ML-прогноз сохраняет преимущество {favorite_name}, но "
                    f"детерминированный Matchup Score склоняется к {matchup_name}. "
                    "Из-за противоречия источников вывод следует считать ограниченным."
                    if language == "ru" else
                    f"The ML prediction favors {favorite_name}, while the deterministic "
                    f"Matchup Score favors {matchup_name}. The conflicting signals limit "
                    "the strength of the conclusion."
                )
            else:
                summary = (
                    f"ML-прогноз сохраняет преимущество {favorite_name}. "
                    "Вывод основан только на доступных данных CS2Eye."
                    if language == "ru" else
                    f"The ML prediction favors {favorite_name}. The conclusion uses only "
                    "the available CS2Eye data."
                )
        return analysis.model_copy(update={"summary": summary})

    @staticmethod
    def _without_ungrounded_items(analysis, errors):
        """Drop only collection items named by deterministic grounding errors."""
        collections = {
            "key_advantages", "counter_arguments", "contradictions", "risks",
            "data_limitations",
        }
        rejected: dict[str, set[int]] = {name: set() for name in collections}
        for error in errors:
            for collection in collections:
                prefix = f"{collection}["
                if not error.location.startswith(prefix):
                    continue
                index_text = error.location[len(prefix):].split("]", 1)[0]
                if index_text.isdigit():
                    rejected[collection].add(int(index_text))
        updates = {
            collection: [
                item for index, item in enumerate(getattr(analysis, collection))
                if index not in rejected[collection]
            ]
            for collection in collections
        }
        return analysis.model_copy(update=updates)

    def _log(
        self,
        context: MatchAnalysisContext,
        attempt: int,
        started: float,
        result: str,
        provider_result: MatchAnalysisProviderResult | None = None,
    ) -> None:
        logger.info(
            "match_llm_analysis match_id=%s team_a_id=%s team_b_id=%s model=%s "
            "prompt_version=%s attempt=%s duration_ms=%.1f result=%s "
            "input_tokens=%s output_tokens=%s",
            context.match.id,
            context.teams.team_a.id,
            context.teams.team_b.id,
            self.model,
            PROMPT_VERSION,
            attempt,
            (perf_counter() - started) * 1000,
            result,
            provider_result.input_tokens if provider_result else None,
            provider_result.output_tokens if provider_result else None,
        )
