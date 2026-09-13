from dataclasses import dataclass
from typing import Protocol

import httpx
from ollama import AsyncClient, RequestError, ResponseError
from pydantic import ValidationError

from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.prompts.match_analysis_registry import get_plan_prompt


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
    analysis: MatchLLMAnalysisV3
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class MatchAnalysisProvider(Protocol):
    async def generate_fixed_plan(
        self, plan: MatchExplanationPlanV2, *, repair_errors: tuple[str, ...] = (),
        previous_analysis: MatchLLMAnalysisV3 | None = None,
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

