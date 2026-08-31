from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from ollama import AsyncClient, RequestError, ResponseError
from pydantic import ValidationError

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.prompts.match_analysis_v2 import build_system_prompt, build_user_input
from cs2eye.prompts.match_analysis_registry import get_plan_prompt
from cs2eye.services.match_llm_analysis_validator import MatchLLMAnalysisValidator


class MatchAnalysisProviderTimeoutError(RuntimeError):
    pass


class MatchAnalysisProviderError(RuntimeError):
    def __init__(self, kind: str = "provider_error") -> None:
        self.kind = kind
        super().__init__("Ollama provider request failed")


class MatchAnalysisInvalidResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchAnalysisProviderResult:
    analysis: MatchLLMAnalysis | MatchLLMAnalysisV2 | MatchLLMAnalysisV3
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class MatchAnalysisProvider(Protocol):
    async def generate(
        self,
        context: MatchAnalysisContext,
        *,
        language: Literal["ru", "en"],
        repair_errors: tuple[str, ...] = (),
        previous_analysis: MatchLLMAnalysis | None = None,
    ) -> MatchAnalysisProviderResult: ...

    async def generate_plan(
        self, plan: MatchExplanationPlan, *, repair_errors: tuple[str, ...] = (),
        previous_analysis: MatchLLMAnalysisV2 | None = None,
    ) -> MatchAnalysisProviderResult: ...


class OllamaMatchAnalysisClient:
    """Ollama async adapter using JSON Schema and Pydantic validation."""

    def __init__(
        self,
        *,
        host: str,
        model: str,
        timeout_seconds: float,
        think: bool = True,
        prompt_version: str = "match_analysis_prompt.v5",
    ) -> None:
        self.model = model
        self.think = think
        self.prompt_version = prompt_version
        get_plan_prompt(prompt_version)
        self._client = AsyncClient(host=host, timeout=timeout_seconds)

    async def close(self) -> None:
        await self._client.close()

    async def generate(
        self,
        context: MatchAnalysisContext,
        *,
        language: Literal["ru", "en"],
        repair_errors: tuple[str, ...] = (),
        previous_analysis: MatchLLMAnalysis | None = None,
    ) -> MatchAnalysisProviderResult:
        allowed_refs, _ = MatchLLMAnalysisValidator.evidence_registry(context)
        output_schema = self._grounded_output_schema(
            context, allowed_refs, repair=bool(repair_errors),
        )
        try:
            response = await self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": build_system_prompt(language)},
                    {
                        "role": "user",
                        "content": build_user_input(
                            context, language, repair_errors, allowed_refs,
                            previous_analysis,
                        ),
                    },
                ],
                format=output_schema,
                options={"temperature": 0},
                think=self.think,
                tools=[],
            )
        except httpx.TimeoutException as error:
            raise MatchAnalysisProviderTimeoutError("Ollama request timed out") from error
        except ConnectionError as error:
            raise MatchAnalysisProviderError("unavailable") from error
        except (RequestError, ResponseError) as error:
            raise MatchAnalysisProviderError("provider_error") from error
        except ValidationError as error:
            raise MatchAnalysisInvalidResponseError(
                "Ollama returned an invalid response envelope"
            ) from error

        try:
            parsed = MatchLLMAnalysis.model_validate_json(response.message.content)
        except (ValidationError, ValueError, TypeError) as error:
            raise MatchAnalysisInvalidResponseError(
                "Ollama did not return a valid MatchLLMAnalysis"
            ) from error

        return MatchAnalysisProviderResult(
            analysis=parsed,
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )

    async def generate_plan(
        self, plan: MatchExplanationPlan, *, repair_errors: tuple[str, ...] = (),
        previous_analysis: MatchLLMAnalysisV2 | None = None,
    ) -> MatchAnalysisProviderResult:
        system_prompt, user_input = get_plan_prompt(self.prompt_version)
        try:
            response = await self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt()},
                    {"role": "user", "content": user_input(
                        plan, repair_errors, previous_analysis,
                    )},
                ],
                format=self._plan_output_schema(plan),
                options={"temperature": 0}, think=self.think, tools=[],
            )
        except httpx.TimeoutException as error:
            raise MatchAnalysisProviderTimeoutError("Ollama request timed out") from error
        except ConnectionError as error:
            raise MatchAnalysisProviderError("unavailable") from error
        except (RequestError, ResponseError) as error:
            raise MatchAnalysisProviderError("provider_error") from error
        except ValidationError as error:
            raise MatchAnalysisInvalidResponseError(
                "Ollama returned an invalid response envelope"
            ) from error
        try:
            parsed = MatchLLMAnalysisV2.model_validate_json(response.message.content)
        except (ValidationError, ValueError, TypeError) as error:
            raise MatchAnalysisInvalidResponseError(
                "Ollama did not return a valid MatchLLMAnalysis v2"
            ) from error
        return MatchAnalysisProviderResult(
            analysis=parsed, input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )

    async def generate_fixed_plan(
        self, plan: MatchExplanationPlanV2, *, repair_errors: tuple[str, ...] = (),
        previous_analysis: MatchLLMAnalysisV3 | None = None,
    ) -> MatchAnalysisProviderResult:
        system_prompt, user_input = get_plan_prompt(self.prompt_version)
        try:
            response = await self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt()},
                    {"role": "user", "content": user_input(plan, repair_errors, previous_analysis)},
                ],
                format=self._fixed_plan_output_schema(),
                options={"temperature": 0}, think=self.think, tools=[],
            )
        except httpx.TimeoutException as error:
            raise MatchAnalysisProviderTimeoutError("Ollama request timed out") from error
        except ConnectionError as error:
            raise MatchAnalysisProviderError("unavailable") from error
        except (RequestError, ResponseError) as error:
            raise MatchAnalysisProviderError("provider_error") from error
        try:
            parsed = MatchLLMAnalysisV3.model_validate_json(response.message.content)
        except (ValidationError, ValueError, TypeError) as error:
            raise MatchAnalysisInvalidResponseError("Ollama did not return a valid MatchLLMAnalysis v3") from error
        return MatchAnalysisProviderResult(
            analysis=parsed, input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )

    @staticmethod
    def _fixed_plan_output_schema() -> dict:
        """Require new-run fields while the Pydantic model reads old snapshots."""
        schema = MatchLLMAnalysisV3.model_json_schema()
        required = schema.setdefault("required", [])
        if "expected_winner_text" not in required:
            required.insert(0, "expected_winner_text")
        return schema

    @staticmethod
    def _plan_output_schema(plan: MatchExplanationPlan) -> dict:
        schema = MatchLLMAnalysisV2.model_json_schema()
        groups = {
            "advantage_texts": plan.advantages,
            "counter_argument_texts": plan.counter_arguments,
            "contradiction_texts": plan.contradictions,
            "risk_texts": plan.risks,
            "limitation_texts": plan.limitations,
        }
        for field, items in groups.items():
            identifiers = []
            required = []
            for item in items:
                identifier = next(
                    getattr(item, name) for name in (
                        "signal_id", "contradiction_id", "risk_id", "limitation_id",
                    ) if hasattr(item, name)
                )
                identifiers.append(identifier)
                if getattr(item, "importance", None) == "high" or getattr(item, "severity", None) == "high":
                    required.append(identifier)
            text_schema = {"type": "string", "minLength": 1, "maxLength": 1000}
            schema["properties"][field] = {
                "type": "object", "additionalProperties": False,
                "properties": {identifier: text_schema for identifier in identifiers},
                "required": required,
            }
        return schema

    @staticmethod
    def _grounded_output_schema(
        context: MatchAnalysisContext, allowed_refs: set[str], *, repair: bool = False,
    ) -> dict:
        """Constrain evidence and immutable business invariants for this context."""
        schema = MatchLLMAnalysis.model_json_schema()

        prediction = context.prediction
        if (
            prediction.status == "available"
            and prediction.team_a_probability is not None
            and prediction.team_b_probability is not None
        ):
            favorite = (
                "none" if prediction.team_a_probability == prediction.team_b_probability
                else "team_a" if prediction.team_a_probability > prediction.team_b_probability
                else "team_b"
            )
        else:
            favorite = "none"
        schema["$defs"]["AnalysisConclusion"]["properties"]["favored_team"] = {
            "type": "string", "enum": [favorite],
        }
        quality = context.data_quality.overall_status
        if quality == "weak":
            schema["properties"]["analysis_status"] = {
                "type": "string", "enum": ["limited"],
            }
        elif quality == "insufficient":
            schema["properties"]["analysis_status"] = {
                "type": "string", "enum": ["insufficient_data"],
            }
            schema["$defs"]["AnalysisConclusion"]["properties"]["confidence"] = {
                "type": "string", "enum": ["insufficient"],
            }
        else:
            schema["properties"]["analysis_status"] = {
                "type": "string", "enum": ["complete", "limited"],
            }
        def visit(node) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict) and "evidence_refs" in properties:
                    evidence_schema = properties["evidence_refs"]
                    evidence_schema["items"] = {
                        "type": "string",
                        "enum": sorted(allowed_refs),
                    }
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(schema)
        # Tie every concrete category to compatible evidence IDs. A global enum
        # prevents invented refs but still lets a small local model attach a real,
        # unrelated ID. These conditionals prevent that at decoding time.
        limitation_refs = schema["$defs"]["DataLimitation"]["properties"]["evidence_refs"]
        limitation_refs["items"] = {"type": "string", "enum": ["data_quality"]}
        limitation_refs["minItems"] = 1
        if MatchLLMAnalysisValidator._ml_matchup_conflict(context):
            schema["properties"]["contradictions"]["minItems"] = 1
            schema["properties"]["contradictions"]["maxItems"] = 1
            # Two unique values drawn from a two-value enum guarantees both refs.
            contradiction_refs = schema["$defs"]["AnalysisContradiction"][
                "properties"
            ]["evidence_refs"]
            contradiction_refs["items"] = {
                "type": "string", "enum": ["prediction", "matchup"],
            }
            contradiction_refs["minItems"] = 2
            contradiction_refs["maxItems"] = 2
            contradiction_refs["uniqueItems"] = True
        return schema
