from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3


class MatchLLMAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_a_id: int
    team_b_id: int
    as_of: datetime
    match_id: int | None = None
    tournament_id: int | None = None
    match_format: Literal["bo1", "bo3", "bo5"] | None = None
    analysis_mode: Literal["pre_match", "post_match"] = "pre_match"
    language: Literal["ru", "en"] = "ru"


class MatchLLMRuntimeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama", "none"]
    model: str
    prompt_version: Literal[
        "match_analysis_prompt.v1", "match_analysis_prompt.v2", "match_analysis_prompt.v3",
        "match_analysis_prompt.v4", "match_analysis_prompt.v5",
    ] = (
        "match_analysis_prompt.v3"
    )
    attempts: int = Field(ge=0, le=2)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    provider_response_id: str | None = None
    schema_valid: bool = True
    business_valid: bool = True
    grounding_valid: bool = True
    repair_attempted: bool = False
    grounding_error_codes: list[str] = Field(default_factory=list)


class MatchLLMAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: MatchAnalysisContext
    explanation_plan: MatchExplanationPlanV2 | None = None
    analysis: MatchLLMAnalysis | MatchLLMAnalysisV3
    runtime: MatchLLMRuntimeMetadata


class MatchLLMStoredAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_run_id: int
    source_run_id: int | None = None
    status: Literal["pending", "completed", "failed", "skipped_insufficient_data"]
    context: MatchAnalysisContext
    explanation_plan: MatchExplanationPlanV2 | None = None
    analysis: MatchLLMAnalysis | MatchLLMAnalysisV3 | None
    runtime: MatchLLMRuntimeMetadata
    error_code: str | None = None
    error_message: str | None = None
    validation_error_codes: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class MatchLLMHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_run_id: int | None = None
    created_at: datetime
    status: Literal["pending", "completed", "failed", "skipped_insufficient_data"]
    provider: str | None
    model: str | None
    prompt_version: str
    as_of: datetime
    analysis_status: str | None
    favored_team: str | None
    confidence: str | None


class MatchLLMRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reuse_context: bool = True
    reuse_explanation_plan: bool = False
    as_of: datetime | None = None
