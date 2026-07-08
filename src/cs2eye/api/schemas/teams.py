from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class TeamRosterMemberCreate(BaseModel):
    nickname: str
    real_name: str | None = None
    country: str | None = None

    status: str = "active"
    role: str | None = None

    joined_at: date | None = None
    left_at: date | None = None

    liquipedia_url: str | None = None
    hltv_id: int | None = None

    current_rating: float | None = None
    player_strength_score: float | None = Field(default=None, ge=0, le=100)

    source_name: str | None = None
    source_url: str | None = None
    source_confidence: float = Field(default=0.7, ge=0, le=1)

    notes: str | None = None


class TeamCreateRequest(BaseModel):
    name: str
    country: str | None = None
    region: str | None = None
    liquipedia_url: str | None = None
    hltv_id: int | None = None

    players: list[TeamRosterMemberCreate] = Field(default_factory=list)


class TeamRosterMemberResponse(BaseModel):
    roster_member_id: UUID

    player_id: UUID
    nickname: str
    real_name: str | None
    country: str | None

    status: str
    role: str | None

    joined_at: date | None
    left_at: date | None

    current_rating: float | None
    player_strength_score: float

    source_name: str | None
    source_url: str | None
    source_confidence: float

    notes: str | None


class TeamStrengthResponse(BaseModel):
    team_id: UUID
    team_name: str

    active_players_count: int
    base_player_score: float

    roster_bonus: float
    roster_penalty: float

    team_strength_score: float

    missing_required_roles: list[str]
    notes: list[str]


class TeamDetailResponse(BaseModel):
    id: UUID
    name: str
    country: str | None
    region: str | None
    liquipedia_url: str | None
    hltv_id: int | None

    roster: list[TeamRosterMemberResponse]
    strength: TeamStrengthResponse


class TeamListItem(BaseModel):
    id: UUID
    name: str
    country: str | None
    region: str | None
    active_players_count: int
    team_strength_score: float


class TeamListResponse(BaseModel):
    items: list[TeamListItem]
    total: int

class TeamRoleComparisonResponse(BaseModel):
    role: str

    team_a_score: float
    team_b_score: float

    team_a_players: list[str]
    team_b_players: list[str]

    advantage_team_name: str | None
    advantage_diff: float

    note: str


class TeamCompareResponse(BaseModel):
    team_a: TeamStrengthResponse
    team_b: TeamStrengthResponse

    strength_advantage_team_name: str | None
    strength_advantage_diff: float

    role_comparisons: list[TeamRoleComparisonResponse]

    summary_notes: list[str]