from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TeamParticipantResponse(BaseModel):
    id: int
    bo3_id: int
    bo3_slug: str
    nickname: str
    image_url: str | None
    country_code: str | None
    country_name: str | None
    participant_type: str
    role: str | None = None
    is_active: bool = True
    joined_at: datetime | None = None
    left_at: datetime | None = None
    player_strength: int | None = None


TeamRole = Literal[
    "igl",
    "awper",
    "entry_frag",
    "lurk",
    "anchor_support",
    "rifler",
]


class TeamParticipantRoleUpdate(BaseModel):
    role: TeamRole | None


class TeamStrengthFactorResponse(BaseModel):
    code: str
    label: str
    kind: str
    value: float
    explanation: str
    players: list[str]


class TeamStrengthResponse(BaseModel):
    active_players_count: int
    base_player_score: float
    roster_bonus: float
    roster_penalty: float
    total_adjustment: float
    score_before_limits: float
    team_strength_score: float
    calculation: str
    missing_required_roles: list[str]
    factors: list[TeamStrengthFactorResponse]
    notes: list[str]


class TeamListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bo3_id: int
    bo3_slug: str
    name: str
    logo_url: str | None
    country_code: str | None
    country_name: str | None
    region: str | None
    current_rank: int | None
    current_points: Decimal | None
    rank_change: int | None
    ranking_date: date | None
    is_analytics_active: bool
    roster_synced_at: datetime | None
    roster: list[TeamParticipantResponse] = Field(
        default_factory=list,
    )


class TeamDetailResponse(TeamListItem):
    strength: TeamStrengthResponse


class TeamComparisonPlayerResponse(BaseModel):
    id: int
    nickname: str
    image_url: str | None
    role: str | None
    bo3_rating: Decimal | None
    player_strength: int | None
    effective_player_strength: int
    strength_is_fallback: bool


class TeamComparisonSideResponse(BaseModel):
    id: int
    bo3_id: int
    bo3_slug: str
    name: str
    logo_url: str | None
    country_code: str | None
    country_name: str | None
    region: str | None
    current_rank: int | None
    current_points: Decimal | None
    rank_change: int | None
    ranking_date: date | None
    roster_synced_at: datetime | None
    active_players_count: int
    roster: list[TeamComparisonPlayerResponse]
    coaches: list[TeamComparisonPlayerResponse]
    strength: TeamStrengthResponse
    relative_strength_percent: float | None


class TeamRoleComparisonResponse(BaseModel):
    role: str
    team_a_score: float | None
    team_b_score: float | None
    team_a_players: list[TeamComparisonPlayerResponse]
    team_b_players: list[TeamComparisonPlayerResponse]
    advantage_team_id: int | None
    advantage_team_name: str | None
    advantage_diff: float | None
    note: str


class TeamRankingComparisonResponse(BaseModel):
    rank_advantage_team_id: int | None
    rank_advantage_team_name: str | None
    rank_difference: int | None
    points_advantage_team_id: int | None
    points_advantage_team_name: str | None
    points_difference: Decimal | None


class TeamComparisonResponse(BaseModel):
    team_a: TeamComparisonSideResponse
    team_b: TeamComparisonSideResponse
    strength_advantage_team_id: int | None
    strength_advantage_team_name: str | None
    strength_advantage_diff: float
    ranking: TeamRankingComparisonResponse
    role_comparisons: list[TeamRoleComparisonResponse]
    summary_notes: list[str]


class RankingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    source: str
    source_url: str
    started_at: datetime
    finished_at: datetime | None
    ranking_date: date | None
    teams_received: int
    teams_activated: int
    teams_deactivated: int
    player_profiles_updated: int
    player_profiles_failed: int
    player_profile_failures: list[dict] = Field(default_factory=list)
    error_message: str | None


class ProbeTeamResponse(BaseModel):
    rank: int
    name: str
    bo3_id: int
    bo3_slug: str
    points: Decimal
    rank_change: int | None
    region: str | None
    roster_size: int


class TopTeamsProbeResponse(BaseModel):
    ranking_date: date
    teams_received: int
    teams: list[ProbeTeamResponse]
