from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from cs2eye.api.schemas.analyst_factors import Category


Probability = Annotated[float, Field(ge=0.0, le=1.0)]
Reliability = Annotated[float, Field(ge=0.0, le=1.0)]
SampleSize = Annotated[int, Field(ge=0)]
Score = float

TeamSide = Literal["team_a", "team_b"]
KnownMatchFormat = Literal["bo1", "bo3", "bo5"]
KnownMatchEnvironment = Literal["lan", "online"]
KnownMatchStage = Literal[
    "group",
    "swiss",
    "round_of_32",
    "round_of_16",
    "quarterfinal",
    "semifinal",
    "final",
]
BracketSection = Literal["main", "upper", "lower", "group", "swiss"]


class MatchAnalysisContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TournamentContext(MatchAnalysisContextModel):
    id: int | None
    name: str | None
    tier: str | None


class MatchContext(MatchAnalysisContextModel):
    id: int | None
    date: date | None
    format: KnownMatchFormat | None
    environment: KnownMatchEnvironment | None
    stage: KnownMatchStage | None
    is_playoff: bool | None
    is_elimination: bool | None
    tournament: TournamentContext
    round_number: Annotated[int, Field(ge=1)] | None
    round_label: str | None
    section: BracketSection | None


class RosterPlayerContext(MatchAnalysisContextModel):
    id: int | None
    name: str
    role: str | None


class RosterCoachContext(MatchAnalysisContextModel):
    id: int | None
    name: str


class TeamRosterContext(MatchAnalysisContextModel):
    roster_id: int | None
    players: list[RosterPlayerContext]
    coach: RosterCoachContext | None
    stability_score: Score | None
    reliability: Reliability | None
    sample_maps: SampleSize


class TeamStrengthKeyFactor(MatchAnalysisContextModel):
    factor_id: str
    key: str
    score: Score | None
    reliability: Reliability | None


class TeamStrengthContext(MatchAnalysisContextModel):
    score: Score | None
    reliability: Reliability | None
    sample_size: SampleSize
    key_factors: list[TeamStrengthKeyFactor]


class TeamFormContext(MatchAnalysisContextModel):
    tournament_form_score: Score | None
    tournament_matches: SampleSize
    tournament_reliability: Reliability | None
    recent_60d_score: Score | None
    recent_60d_matches: SampleSize
    recent_60d_reliability: Reliability | None
    strength_of_schedule_score: Score | None
    performance_vs_expectation_score: Score | None
    matches_vs_top_5: SampleSize
    matches_vs_top_10: SampleSize
    matches_vs_top_30: SampleSize


class TeamLeadershipContext(MatchAnalysisContextModel):
    igl_score: Score | None
    coach_score: Score | None
    reliability: Reliability | None
    sample_size: SampleSize


class AnalysisTeamContext(MatchAnalysisContextModel):
    id: int | None
    name: str | None
    rank: Annotated[int, Field(ge=1)] | None
    roster: TeamRosterContext
    team_strength: TeamStrengthContext
    form: TeamFormContext
    leadership: TeamLeadershipContext


class TeamsContext(MatchAnalysisContextModel):
    team_a: AnalysisTeamContext
    team_b: AnalysisTeamContext


class EvidenceOpponent(MatchAnalysisContextModel):
    id: int | None
    name: str | None
    rank: Annotated[int, Field(ge=1)] | None


class RecentSeriesEvidence(MatchAnalysisContextModel):
    evidence_id: str
    date: date | None
    tournament: str | None
    opponent: EvidenceOpponent
    result: Literal["win", "loss"] | None
    series_score: str | None
    expected_win_probability: Probability | None
    performance_vs_expectation: float | None
    current_tournament: bool | None
    reliability: Reliability | None


class RecentSeriesEvidenceContext(MatchAnalysisContextModel):
    team_a: list[RecentSeriesEvidence]
    team_b: list[RecentSeriesEvidence]


class ModelDriver(MatchAnalysisContextModel):
    driver_id: str
    key: str
    favored_team: TeamSide | None
    importance: float | None
    reliability: Reliability | None


class PredictionContext(MatchAnalysisContextModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: Literal["ml_prediction"] = "ml_prediction"
    status: Literal[
        "available",
        "not_available",
        "model_not_trained",
        "insufficient_data",
    ]
    model_version: str | None
    quality_gate_passed: bool | None
    team_a_probability: Probability | None
    team_b_probability: Probability | None
    confidence: Reliability | None
    top_model_drivers: list[ModelDriver]


class MatchupFactor(MatchAnalysisContextModel):
    factor_id: str
    key: str
    team_a_score: Score | None
    team_b_score: Score | None
    reliability: Reliability | None
    sample_size: SampleSize | None


class MatchupContext(MatchAnalysisContextModel):
    source_type: Literal["deterministic_analytics"] = "deterministic_analytics"
    model_version: str | None
    team_a_score: Score | None
    team_b_score: Score | None
    reliability: Reliability | None
    factors: list[MatchupFactor]


class LikelyMap(MatchAnalysisContextModel):
    map: str
    series_probability: Probability | None
    confidence: Reliability | None
    likely_role: Literal["team_a_pick", "team_b_pick", "decider", "unknown"]


class VetoContext(MatchAnalysisContextModel):
    source_type: Literal["deterministic_analytics"] = "deterministic_analytics"
    basis: Literal["calculated_veto"] = "calculated_veto"
    model_version: str | None
    likely_maps: list[LikelyMap]


class MapTeamStrength(MatchAnalysisContextModel):
    map_strength: Score | None
    reliability: Reliability | None
    sample_maps: SampleSize


class MapKeyEdge(MatchAnalysisContextModel):
    evidence_id: str
    metric: str
    favored_team: TeamSide
    strength: Literal["small", "moderate", "clear"]
    reliability: Reliability | None


class MapMatchupContext(MatchAnalysisContextModel):
    map: str
    relevance: Probability | None
    team_a: MapTeamStrength
    team_b: MapTeamStrength
    matchup_score_team_a: Score | None
    key_edges: list[MapKeyEdge]


class H2HScopeContext(MatchAnalysisContextModel):
    status: Literal[
        "available",
        "no_meetings",
        "partial_data",
        "roster_unavailable",
    ]
    series_played: SampleSize
    maps_played: SampleSize
    team_a_series_won: SampleSize
    team_b_series_won: SampleSize
    team_a_maps_won: SampleSize
    team_b_maps_won: SampleSize
    team_a_rating: Score | None
    team_b_rating: Score | None
    team_a_score: Score | None
    team_b_score: Score | None
    confidence: Reliability | None


class H2HContext(MatchAnalysisContextModel):
    preferred_scope: Literal["organizations", "current_rosters"]
    history_applicability: Literal["high", "medium", "low", "none"]
    organizations: H2HScopeContext
    current_rosters: H2HScopeContext


class ManualAnalystNote(MatchAnalysisContextModel):
    note_id: str
    polarity: Literal["positive", "negative", "neutral"]
    category: Category | None
    players: list[str]
    coach: str | None
    map: str | None
    environment: KnownMatchEnvironment | None
    text: str


class ManualContext(MatchAnalysisContextModel):
    source_type: Literal["manual_analyst_note"] = "manual_analyst_note"
    team_a: list[ManualAnalystNote]
    team_b: list[ManualAnalystNote]


class DataQualityContext(MatchAnalysisContextModel):
    overall_status: Literal["available", "partial", "weak", "insufficient"]
    limitations: list[str]
    missing_sections: list[str]
    warnings: list[str]


class MatchAnalysisContext(MatchAnalysisContextModel):
    schema_version: Literal["match_analysis_context.v1"] = "match_analysis_context.v1"
    generated_at: datetime
    as_of: datetime
    analysis_mode: Literal["pre_match", "post_match"]
    match: MatchContext
    teams: TeamsContext
    recent_series_evidence: RecentSeriesEvidenceContext
    prediction: PredictionContext
    matchup: MatchupContext
    veto: VetoContext
    map_matchups: list[MapMatchupContext]
    h2h: H2HContext
    manual_context: ManualContext
    data_quality: DataQualityContext
