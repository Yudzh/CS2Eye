from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.api.schemas.match_llm_runtime import (
    MatchLLMAnalysisResponse,
    MatchLLMRuntimeMetadata,
)
from cs2eye.services.deterministic_match_explanation_builder_v2 import (
    DeterministicMatchExplanationBuilderV2,
)
from cs2eye.services.match_llm_analysis_v3_validator import (
    MatchLLMAnalysisV3Validator, MatchLLMV3ValidationError,
)
from cs2eye.services.match_analysis_context_builder import MatchAnalysisContextBuilder
from cs2eye.services.ollama_match_analysis_client import (
    MatchAnalysisInvalidResponseError,
    MatchAnalysisProvider,
    MatchAnalysisProviderError,
    MatchAnalysisProviderTimeoutError,
)


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
    ) -> None:
        self.builder = builder
        self.provider = provider
        self.enabled = enabled
        self.model = model
        self.explanation_builder = DeterministicMatchExplanationBuilderV2()
        self.v3_validator = MatchLLMAnalysisV3Validator()

    async def explain_context(
        self, context: MatchAnalysisContext,
        plan: MatchExplanationPlanV2 | None = None,
    ) -> MatchLLMAnalysisResponse:
        """Deterministic analytics first, text-only LLM wording second."""
        plan = plan or self.explanation_builder.build(context)
        return await self._explain_fixed_context(context, plan)

    async def _explain_fixed_context(
        self, context: MatchAnalysisContext, plan: MatchExplanationPlanV2,
    ) -> MatchLLMAnalysisResponse:
        if not self.enabled or self.provider is None:
            raise MatchLLMServiceError(
                "llm_not_configured", "Match LLM analysis is disabled or Ollama is not configured.",
            )
        if not hasattr(self.provider, "generate_fixed_plan"):
            raise MatchLLMServiceError(
                "llm_provider_error", "Provider does not support MatchExplanationPlan v2.",
            )
        input_tokens = output_tokens = 0
        known = False
        repair_errors: tuple[str, ...] = ()
        previous: MatchLLMAnalysisV3 | None = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                latest = await self.provider.generate_fixed_plan(
                    plan, repair_errors=repair_errors, previous_analysis=previous,
                )
            except MatchAnalysisProviderTimeoutError as error:
                raise MatchLLMServiceError("llm_timeout", str(error), attempts=attempt) from error
            except MatchAnalysisInvalidResponseError as error:
                raise MatchLLMServiceError("llm_invalid_response", str(error), attempts=attempt) from error
            except MatchAnalysisProviderError as error:
                raise MatchLLMServiceError("llm_provider_error", str(error), attempts=attempt) from error
            if latest.input_tokens is not None:
                input_tokens += latest.input_tokens; known = True
            if latest.output_tokens is not None:
                output_tokens += latest.output_tokens; known = True
            if not isinstance(latest.analysis, MatchLLMAnalysisV3):
                raise MatchLLMServiceError("llm_invalid_response", "Provider returned wrong fixed analysis schema.", attempts=attempt)
            normalized_analysis = self._normalize_fixed_analysis(plan, latest.analysis)
            try:
                self.v3_validator.validate(plan, normalized_analysis)
            except MatchLLMV3ValidationError as error:
                if attempt == self.MAX_ATTEMPTS:
                    raise MatchLLMServiceError(
                        "llm_validation_failed", "Ollama fixed wording failed validation after repair.",
                        attempts=attempt, input_tokens=input_tokens or None,
                        output_tokens=output_tokens or None, schema_valid=True,
                        business_valid=True, repair_attempted=True,
                        validation_errors=error.errors, validation_error_codes=error.codes,
                    ) from error
                repair_errors = error.errors; previous = normalized_analysis; continue
            return MatchLLMAnalysisResponse(
                context=context, explanation_plan=plan,
                analysis=normalized_analysis,
                runtime=MatchLLMRuntimeMetadata(
                    provider="ollama", model=self.model,
                    prompt_version=getattr(self.provider, "prompt_version", "match_analysis_prompt.v5"),
                    attempts=attempt,
                    input_tokens=input_tokens if known else None,
                    output_tokens=output_tokens if known else None,
                    repair_attempted=attempt > 1,
                ),
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _normalize_fixed_analysis(
        plan: MatchExplanationPlanV2, analysis: MatchLLMAnalysisV3,
    ) -> MatchLLMAnalysisV3:
        """Enforce presentation-only deterministic facts before validation.

        This does not alter analytics: expected winner comes verbatim from the
        plan, and manual notes only receive their mandatory source label.
        """
        expected = plan.expected_winner
        expected_text = (
            f"По расчётам должна выиграть {expected.team_name} — "
            f"{expected.win_probability:.2%}."
            if expected is not None else "Расчёт победителя недоступен."
        )
        manual_text = analysis.manual_text
        if plan.manual_context.team_a or plan.manual_context.team_b:
            lowered = manual_text.casefold()
            if "ручн" not in lowered or "аналит" not in lowered:
                manual_text = f"Ручные комментарии аналитика: {manual_text}"
        return analysis.model_copy(update={
            "expected_winner_text": expected_text,
            "manual_text": manual_text,
        })

