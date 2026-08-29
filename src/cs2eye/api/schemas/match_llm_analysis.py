from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


AnalysisStatus = Literal["complete", "limited", "insufficient_data"]
AnalysisSide = Literal["team_a", "team_b", "neutral"]
FavoredTeam = Literal["team_a", "team_b", "none"]
Advantage = Literal["none", "small", "moderate", "clear"]
AnalysisConfidence = Literal["high", "medium", "low", "insufficient"]
Importance = Literal["high", "medium", "low"]
Severity = Literal["high", "medium", "low"]
EvidenceKind = Literal[
    "statistical", "ml", "deterministic", "manual", "mixed", "data_quality",
]
ClaimCategory = Literal[
    "overall_strength",
    "recent_form",
    "tournament_form",
    "strength_of_schedule",
    "performance_vs_expectation",
    "roster",
    "map_pool",
    "veto",
    "ct_side",
    "t_side",
    "economy",
    "opening",
    "trade",
    "clutch",
    "postplant",
    "retake",
    "leadership",
    "h2h",
    "ml_prediction",
    "matchup",
    "manual_context",
    "data_quality",
    "other",
]

EvidenceRefs = Annotated[list[str], Field(min_length=1)]
Statement = Annotated[str, Field(min_length=1, max_length=1000)]


class MatchLLMAnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisConclusion(MatchLLMAnalysisModel):
    favored_team: FavoredTeam
    advantage: Advantage
    confidence: AnalysisConfidence
    reasoning_basis: Literal["ml_prediction"] = "ml_prediction"


class AnalysisClaim(MatchLLMAnalysisModel):
    claim_id: str
    side: AnalysisSide
    category: ClaimCategory
    importance: Importance
    statement: Statement
    evidence_refs: EvidenceRefs
    evidence_kind: EvidenceKind | None = None


class AnalysisContradiction(MatchLLMAnalysisModel):
    contradiction_id: str
    importance: Importance
    description: Statement
    evidence_refs: EvidenceRefs


class AnalysisRisk(MatchLLMAnalysisModel):
    risk_id: str
    severity: Severity
    category: ClaimCategory
    statement: Statement
    evidence_refs: EvidenceRefs
    evidence_kind: EvidenceKind | None = None


class DataLimitation(MatchLLMAnalysisModel):
    limitation_id: str
    severity: Severity
    statement: Statement
    evidence_refs: EvidenceRefs
    evidence_kind: EvidenceKind | None = None


class MatchLLMAnalysis(MatchLLMAnalysisModel):
    schema_version: Literal["match_llm_analysis.v1"] = "match_llm_analysis.v1"
    context_schema_version: Literal["match_analysis_context.v1"] = (
        "match_analysis_context.v1"
    )
    analysis_status: AnalysisStatus
    conclusion: AnalysisConclusion
    key_advantages: Annotated[list[AnalysisClaim], Field(max_length=5)]
    counter_arguments: Annotated[list[AnalysisClaim], Field(max_length=5)]
    contradictions: Annotated[list[AnalysisContradiction], Field(max_length=3)]
    risks: Annotated[list[AnalysisRisk], Field(max_length=5)]
    data_limitations: list[DataLimitation]
    summary: Annotated[str, Field(max_length=1500)]
