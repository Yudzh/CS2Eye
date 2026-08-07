from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer


AggregationLevel = Literal["organization", "current_roster"]
StrengthStatus = Literal["available", "not_enough_data"]
ConfidenceLevel = Literal[
    "not_enough_data", "low_confidence", "medium_confidence", "high_confidence",
]


class MapStrengthFactorResponse(BaseModel):
    code: str
    label: str
    score: float | None
    configured_weight: float
    effective_weight: float
    impact: float
    explanation: str


class MapStrengthResponse(BaseModel):
    status: StrengthStatus
    map_strength_score: float | None
    performance_score: float | None
    confidence_score: float
    confidence_level: ConfidenceLevel
    factors: list[MapStrengthFactorResponse]
    warnings: list[str]


class SideScopeResponse(BaseModel):
    rounds_played: int
    rounds_won: int
    rounds_lost: int
    win_rate: float | None


class TeamMapScopeResponse(BaseModel):
    maps_played: int
    maps_won: int
    maps_lost: int
    map_win_rate: float | None
    rounds_played: int
    rounds_won: int
    rounds_lost: int
    round_win_rate: float | None
    ct: SideScopeResponse
    t: SideScopeResponse
    overtime_maps: int
    overtime_rounds_played: int
    overtime_rounds_won: int
    sample_size_score: float
    sample_size_label: str
    freshness_score: float
    freshness_label: str
    first_match_date: date | None
    last_match_date: date | None


class RecentTeamMapScopeResponse(TeamMapScopeResponse):
    requested_window: int
    actual_sample: int


class TeamMapRecentResponse(BaseModel):
    last_5: RecentTeamMapScopeResponse | None
    last_10: RecentTeamMapScopeResponse | None
    last_20: RecentTeamMapScopeResponse | None


class TeamMapVersusResponse(BaseModel):
    top_15: TeamMapScopeResponse | None
    top_16_30: TeamMapScopeResponse | None
    tier_2_3: TeamMapScopeResponse | None


class TeamMapResponse(BaseModel):
    map_name: str
    all: TeamMapScopeResponse
    recent: TeamMapRecentResponse
    versus: TeamMapVersusResponse
    strength: MapStrengthResponse


class AnalysisTeamResponse(BaseModel):
    id: int
    name: str
    rank: int | None


class RosterSampleResponse(BaseModel):
    maps_played: int
    first_match_date: date | None
    last_match_date: date | None


class TeamMapsResponse(BaseModel):
    team: AnalysisTeamResponse
    aggregation_level: AggregationLevel
    roster_id: int | None
    status: str
    roster_sample: RosterSampleResponse | None
    maps: list[TeamMapResponse]


class RecentMapMatchResponse(BaseModel):
    demo_file_id: int
    match_date: date | None
    opponent_team_id: int | None
    opponent_team_name: str | None
    opponent_rank: int | None
    opponent_rank_group: str
    score_for: int
    score_against: int
    result: Literal["win", "loss"]
    ct_rounds_won: int
    ct_rounds_played: int
    t_rounds_won: int
    t_rounds_played: int


class TeamMapDetailResponse(BaseModel):
    team: AnalysisTeamResponse
    aggregation_level: AggregationLevel
    roster_id: int | None
    status: str = "available"
    map_name: str
    all: TeamMapScopeResponse | None = None
    recent: TeamMapRecentResponse | None = None
    versus: TeamMapVersusResponse | None = None
    strength: MapStrengthResponse | None = None
    recent_matches: list[RecentMapMatchResponse]


class MapComparisonTeamResponse(BaseModel):
    maps_played: int
    maps_won: int
    maps_lost: int
    map_win_rate: float | None
    map_strength_score: float | None
    confidence_score: float
    confidence_level: ConfidenceLevel
    status: StrengthStatus


ComparisonStatus = Literal[
    "comparable", "team_a_no_data", "team_b_no_data", "both_no_data",
    "team_a_not_enough_data", "team_b_not_enough_data", "both_not_enough_data",
]


class TeamMapComparisonItemResponse(BaseModel):
    map_name: str
    team_a: MapComparisonTeamResponse | None
    team_b: MapComparisonTeamResponse | None
    comparison_status: ComparisonStatus
    advantage_team_id: int | None
    advantage_team_name: str | None
    advantage_diff: float | None
    advantage_level: Literal["none", "small", "clear", "strong"] | None


class MapComparisonTeamMetaResponse(BaseModel):
    id: int
    name: str
    rank: int | None
    roster_id: int | None


class TeamMapComparisonSummaryResponse(BaseModel):
    team_a_advantage_maps: int
    team_b_advantage_maps: int
    close_maps: int
    not_comparable_maps: int


class TeamMapComparisonResponse(BaseModel):
    aggregation_level: AggregationLevel
    team_a: MapComparisonTeamMetaResponse
    team_b: MapComparisonTeamMetaResponse
    status: str
    maps: list[TeamMapComparisonItemResponse]
    summary: TeamMapComparisonSummaryResponse


class H2HResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", check_fields=False)
    def round_h2h_floats(self, value: object) -> object:
        return round(value, 2) if isinstance(value, float) else value


class TeamH2HTeamResponse(H2HResponseModel):
    id: int
    name: str
    current_roster_id: int | None


class TeamH2HTeamMetricsResponse(H2HResponseModel):
    maps_won: int
    map_win_rate: float | None
    weighted_map_win_rate: float | None
    rounds_won: int
    round_win_rate: float | None
    weighted_round_win_rate: float | None
    performance_score: float | None
    h2h_rating: float | None


class TeamH2HMapBreakdownResponse(H2HResponseModel):
    map_name: str
    maps_played: int
    team_a_maps_won: int
    team_b_maps_won: int
    team_a_map_win_rate: float
    team_b_map_win_rate: float
    team_a_rounds_won: int
    team_b_rounds_won: int
    team_a_round_win_rate: float
    team_b_round_win_rate: float
    first_meeting_date: date
    last_meeting_date: date
    overtime_maps: int


class TeamH2HRecentMapResponse(H2HResponseModel):
    demo_file_id: int
    match_date: date
    tournament: str
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_team_id: int
    went_to_overtime: bool
    team_a_roster_id: int | None
    team_b_roster_id: int | None
    recency_weight: float


class TeamH2HFactorResponse(H2HResponseModel):
    code: str
    score: float
    weight: float
    explanation: str


class TeamH2HSliceResponse(H2HResponseModel):
    status: Literal["available", "no_meetings", "current_roster_unavailable", "current_rosters_never_met", "partial_data"]
    candidate_maps_count: int
    included_maps_count: int
    excluded_maps_count: int
    maps_played: int
    effective_maps: float
    sample_label: Literal["no_data", "very_small", "small", "medium", "sufficient"]
    confidence_score: float
    confidence_level: Literal["no_data", "low", "medium", "high"]
    first_meeting_date: date | None
    last_meeting_date: date | None
    team_a: TeamH2HTeamMetricsResponse
    team_b: TeamH2HTeamMetricsResponse
    advantage_team_id: int | None
    advantage_team_name: str | None
    advantage_diff: float | None
    advantage_level: Literal["none", "small", "clear", "strong"]
    maps: list[TeamH2HMapBreakdownResponse]
    recent_maps: list[TeamH2HRecentMapResponse]
    factors: list[TeamH2HFactorResponse]
    warnings: list[str]
    series_played: int
    team_a_series_won: int
    team_b_series_won: int


class TeamH2HPlayerExperienceResponse(H2HResponseModel):
    player_id: int | None
    nickname: str
    maps_against_opponent: int
    has_h2h_experience: bool


class TeamH2HPlayerContextResponse(H2HResponseModel):
    current_roster_id: int | None
    current_players_count: int
    players_with_h2h_experience_count: int
    players_without_h2h_experience_count: int
    experience_coverage_percent: float | None
    average_maps_per_current_player: float | None
    experience_data_status: Literal["available", "partial", "unavailable"]
    players: list[TeamH2HPlayerExperienceResponse]


class TeamH2HLatestRosterOverlapResponse(H2HResponseModel):
    status: Literal["available", "unavailable"]
    latest_h2h_roster_id: int | None
    current_roster_id: int | None
    latest_roster_players_count: int
    current_roster_players_count: int
    retained_players_count: int
    changed_players_count: int
    retained_players: list[TeamH2HPlayerExperienceResponse]
    new_current_players: list[TeamH2HPlayerExperienceResponse]
    former_players: list[TeamH2HPlayerExperienceResponse]


class TeamH2HRosterTeamContextResponse(H2HResponseModel):
    experience: TeamH2HPlayerContextResponse
    latest_roster_overlap: TeamH2HLatestRosterOverlapResponse


class TeamH2HRosterContextResponse(H2HResponseModel):
    team_a: TeamH2HRosterTeamContextResponse
    team_b: TeamH2HRosterTeamContextResponse
    history_applicability: Literal["direct", "high", "medium", "low", "unknown"]


class TeamH2HInsightResponse(H2HResponseModel):
    code: str
    text: str


class TeamH2HComparisonResponse(H2HResponseModel):
    status: str
    team_a: TeamH2HTeamResponse
    team_b: TeamH2HTeamResponse
    organizations: TeamH2HSliceResponse
    current_rosters: TeamH2HSliceResponse
    roster_context: TeamH2HRosterContextResponse
    insights: list[TeamH2HInsightResponse]


class LegacyRosterPlayerResponse(BaseModel):
    id: int | None
    name: str
    role: str | None


class LegacyRosterTeamResponse(BaseModel):
    id: int
    name: str
    current_roster_id: int | None
    players: list[LegacyRosterPlayerResponse]


class LegacyHeadToHeadResponse(BaseModel):
    maps_played: int
    team_a_maps_won: int
    team_b_maps_won: int
    team_a_rounds_won: int
    team_b_rounds_won: int
    first_meeting_date: date | None
    last_meeting_date: date | None


class LegacyCurrentRosterComparisonResponse(BaseModel):
    status: str
    reason: str | None = None
    met: bool = False
    team_a: LegacyRosterTeamResponse
    team_b: LegacyRosterTeamResponse
    head_to_head: LegacyHeadToHeadResponse | None
    maps: list[TeamH2HMapBreakdownResponse]
    recent_maps: list[TeamH2HRecentMapResponse]
