from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cs2eye.api.schemas.match_llm_analysis import Advantage, AnalysisConfidence, FavoredTeam


class FixedPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FixedConclusion(FixedPlanModel):
    team_a_name: str
    team_b_name: str
    favored_team: FavoredTeam
    favored_team_name: str | None
    advantage: Advantage
    confidence: AnalysisConfidence
    ml_probability_team_a: float | None = Field(default=None, ge=0, le=1)
    ml_probability_team_b: float | None = Field(default=None, ge=0, le=1)
    internal_statistics_disclaimer: str


class ExpectedWinner(FixedPlanModel):
    team_id: int
    team_name: str
    win_probability: float = Field(ge=0, le=1)


class FormEvidence(FixedPlanModel):
    evidence_id: str
    date: str | None
    tournament: str | None
    opponent: str | None
    opponent_rank: int | None = Field(default=None, ge=1)
    result: Literal["win", "loss"] | None
    series_score: str | None
    performance_vs_expectation: float | None


class PreviousTournamentFallback(FixedPlanModel):
    tournament: str
    matches: int = Field(ge=1)
    evidence: list[FormEvidence]


class TournamentFormTeam(FixedPlanModel):
    team_name: str
    form_level: Literal["strong", "good", "mixed", "weak", "unknown"]
    reliability: float | None = Field(default=None, ge=0, le=1)
    matches: int = Field(ge=0)
    score: float | None = None
    performance_vs_expectation: float | None = None
    evidence: list[FormEvidence]
    previous_tournament: PreviousTournamentFallback | None = None
    fallback: Literal["none", "previous_tournament", "recent_60d", "insufficient"]


class FormComparison(FixedPlanModel):
    favored_team: FavoredTeam
    favored_team_name: str | None
    strength: Literal["none", "small", "moderate", "clear"]


class TournamentFormSection(FixedPlanModel):
    state: Literal["current_tournament", "not_started", "mixed_availability", "fallback", "insufficient"]
    team_a: TournamentFormTeam
    team_b: TournamentFormTeam
    comparison: FormComparison
    context_notes: list[str]


class MapProfileItem(FixedPlanModel):
    map: str
    strength_score: float
    reliability: float = Field(ge=0, le=1)
    sample_maps: int = Field(ge=0)
    classification: Literal["strong", "weak"]


class TeamMapProfile(FixedPlanModel):
    team_name: str
    strong_maps: Annotated[list[MapProfileItem], Field(max_length=3)]
    weak_maps: Annotated[list[MapProfileItem], Field(max_length=3)]


MapReasonType = Literal[
    "team_strong_on_map", "team_weak_on_map", "opponent_strong_on_map",
    "opponent_weak_on_map", "opponent_low_sample", "team_low_sample",
    "ct_side", "t_side", "opening", "trading", "clutch", "postplant", "retake",
    "full_buy", "force_buy", "anti_eco", "pistol", "utility",
]


class MapEdgeReason(FixedPlanModel):
    type: MapReasonType
    side: Literal["team_a", "team_b"]
    side_name: str
    strength: Literal["small", "moderate", "clear"]
    reliability: float | None = Field(default=None, ge=0, le=1)
    evidence_id: str | None = None


class KeyMapEdge(FixedPlanModel):
    map: str
    favored_team: Literal["team_a", "team_b"]
    favored_team_name: str
    strength: Literal["small", "moderate", "clear"]
    relevance: float | None = Field(default=None, ge=0, le=1)
    reasons: Annotated[list[MapEdgeReason], Field(min_length=1, max_length=5)]


class MapsSection(FixedPlanModel):
    status: Literal["available", "insufficient"]
    team_a: TeamMapProfile
    team_b: TeamMapProfile
    key_map_edges: Annotated[list[KeyMapEdge], Field(max_length=3)]
    context_notes: list[str]


TeamplayCategory = Literal[
    "ct_side", "t_side", "opening", "opening_conversion", "trading", "clutch",
    "postplant", "retake", "pistol", "pistol_conversion", "force_buy", "full_buy",
    "anti_eco", "utility", "round_swing", "player_swing",
]


class TeamplaySignal(FixedPlanModel):
    signal_id: str
    category: TeamplayCategory
    side: Literal["team_a", "team_b"]
    side_name: str
    effect: Literal["positive", "negative"]
    strength: Literal["small", "moderate", "clear"]
    reliability: float = Field(ge=0, le=1)
    fact_type: str
    map: str | None = None
    evidence_id: str


class TeamplaySection(FixedPlanModel):
    signals: Annotated[list[TeamplaySignal], Field(max_length=5)]
    context_notes: list[str]


class FixedManualNote(FixedPlanModel):
    note_id: str
    team_name: str
    polarity: Literal["positive", "negative", "neutral"]
    players: list[str]
    coach: str | None
    map: str | None
    text: str


class ManualContextSection(FixedPlanModel):
    team_a: list[FixedManualNote]
    team_b: list[FixedManualNote]
    empty_message: str | None


class MatchExplanationPlanV2(FixedPlanModel):
    schema_version: Literal["match_explanation_plan.v2"] = "match_explanation_plan.v2"
    context_schema_version: Literal["match_analysis_context.v1"] = "match_analysis_context.v1"
    # Optional only for backward-compatible reading of early v2 snapshots.
    expected_winner: ExpectedWinner | None = None
    conclusion: FixedConclusion
    form: TournamentFormSection
    maps: MapsSection
    teamplay: TeamplaySection
    manual_context: ManualContextSection
