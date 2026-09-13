from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3


class QualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMQualityExpectations(QualityModel):
    """Literal facts (map names, key phrases) that a case's wording must surface.

    Structural correctness (grounding, no hallucinated facts, no reversed
    favorites/edges) is already fully covered by MatchLLMAnalysisV3Validator,
    which every case is validated against regardless of these expectations.
    """

    must_mention: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    expected_favored_team: Literal["team_a", "team_b", "none"]
    expected_confidence: Literal["high", "medium", "low", "insufficient"]


class LLMQualityCase(QualityModel):
    case_id: str
    name: str
    description: str
    explanation_plan_snapshot: MatchExplanationPlanV2
    expectations: LLMQualityExpectations
    tags: Annotated[list[str], Field(min_length=1)]
    golden: bool = False
    language: Literal["ru"] = "ru"


class LLMQualityDataset(QualityModel):
    schema_version: Literal["llm_quality_dataset.v2"] = "llm_quality_dataset.v2"
    cases: Annotated[list[LLMQualityCase], Field(min_length=1)]


class LLMQualityMetrics(QualityModel):
    coverage_score: float = Field(ge=0, le=1)
    grounding_pass: bool
    repetition_score: float = Field(ge=0, le=1)
    specificity_score: float = Field(ge=0, le=1)
    conciseness_score: float = Field(ge=0, le=1)
    language_pass: bool
    format_pass: bool
    forbidden_wording_pass: bool
    quality_score: float = Field(ge=0, le=100)
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)


class LLMQualityConfiguration(QualityModel):
    provider: str
    model: str
    prompt_version: str
    reasoning: dict[str, Any] = Field(default_factory=dict)


class LLMQualityRunResult(QualityModel):
    id: int | None = None
    case_id: str
    dataset_version: str
    configuration: LLMQualityConfiguration
    explanation_plan_snapshot: MatchExplanationPlanV2
    llm_output_snapshot: MatchLLMAnalysisV3 | None = None
    deterministic_metrics: LLMQualityMetrics | None = None
    quality_score: float | None = None
    status: Literal["completed", "failed"]
    error_code: str | None = None
    created_at: datetime | None = None


class LLMQualityAggregateReport(QualityModel):
    dataset_version: str
    configuration: LLMQualityConfiguration
    cases: int
    completed: int
    valid: int
    grounding_pass_rate: float
    coverage_average: float
    repetition_average: float
    specificity_average: float
    conciseness_average: float
    language_pass_rate: float
    format_pass_rate: float
    average_quality: float
    repetition_failures: int
    language_failures: int
    manual_good: int = 0
    manual_reviewed: int = 0


class LLMQualityComparison(QualityModel):
    left: LLMQualityAggregateReport
    right: LLMQualityAggregateReport
    deltas: dict[str, float]


class LLMQualityReviewCreate(QualityModel):
    rating: Literal["good", "acceptable", "bad"]
    language_quality: Literal["good", "acceptable", "bad"]
    clarity: Literal["good", "acceptable", "bad"]
    usefulness: Literal["good", "acceptable", "bad"]
    missing_important_point: bool = False
    incorrect_emphasis: bool = False
    too_verbose: bool = False
    too_generic: bool = False
    notes: str | None = Field(default=None, max_length=4000)


class LLMQualityReviewResponse(LLMQualityReviewCreate):
    id: int
    quality_run_id: int
    created_at: datetime
