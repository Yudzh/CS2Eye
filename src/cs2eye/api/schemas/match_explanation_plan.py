from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cs2eye.api.schemas.match_llm_analysis import (
    Advantage, AnalysisConfidence, ClaimCategory, FavoredTeam, Importance, Severity,
)


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExplanationConclusion(PlanModel):
    favored_team: FavoredTeam
    advantage: Advantage
    confidence: AnalysisConfidence
    ml_probability_team_a: float | None = Field(default=None, ge=0, le=1)
    ml_probability_team_b: float | None = Field(default=None, ge=0, le=1)


class ExplanationFact(PlanModel):
    type: str
    text_key: str
    values: dict[str, Any] = Field(default_factory=dict)


class ExplanationSignal(PlanModel):
    signal_id: str
    side: Literal["team_a", "team_b"]
    category: ClaimCategory
    direction: Literal["supports_favorite", "against_favorite"]
    strength: Literal["small", "moderate", "strong"]
    importance: Importance
    reliability: float = Field(ge=0, le=1)
    sample_size: int | None = Field(default=None, ge=0)
    evidence_refs: Annotated[list[str], Field(min_length=1)]
    facts: Annotated[list[ExplanationFact], Field(min_length=1)]
    source_kind: Literal["statistical", "ml", "deterministic", "manual"]


class ExplanationContradiction(PlanModel):
    contradiction_id: str
    category: Literal[
        "ml_vs_matchup", "strength_vs_form", "organization_vs_roster_h2h",
        "overall_vs_relevant_maps",
    ]
    importance: Importance
    left_ref: str
    right_ref: str
    left_side: Literal["team_a", "team_b"]
    right_side: Literal["team_a", "team_b"]
    facts: Annotated[list[ExplanationFact], Field(min_length=1)]


class ExplanationRisk(PlanModel):
    risk_id: str
    category: ClaimCategory
    severity: Severity
    evidence_refs: Annotated[list[str], Field(min_length=1)]
    facts: Annotated[list[ExplanationFact], Field(min_length=1)]


class ExplanationLimitation(PlanModel):
    limitation_id: str
    category: ClaimCategory
    severity: Severity
    evidence_refs: Annotated[list[str], Field(min_length=1)]
    facts: Annotated[list[ExplanationFact], Field(min_length=1)]


class SupportingContext(PlanModel):
    team_a_name: str | None
    team_b_name: str | None
    tournament: str | None
    format: str | None


class MatchExplanationPlan(PlanModel):
    schema_version: Literal["match_explanation_plan.v1"] = "match_explanation_plan.v1"
    context_schema_version: Literal["match_analysis_context.v1"] = "match_analysis_context.v1"
    status: Literal["complete", "limited", "insufficient_data"]
    conclusion: ExplanationConclusion
    advantages: Annotated[list[ExplanationSignal], Field(max_length=5)]
    counter_arguments: Annotated[list[ExplanationSignal], Field(max_length=5)]
    contradictions: Annotated[list[ExplanationContradiction], Field(max_length=3)]
    risks: Annotated[list[ExplanationRisk], Field(max_length=5)]
    limitations: list[ExplanationLimitation]
    supporting_context: SupportingContext
