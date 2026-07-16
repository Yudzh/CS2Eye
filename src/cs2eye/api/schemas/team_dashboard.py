from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from cs2eye.api.schemas.teams import (
    TeamRosterMemberResponse,
    TeamStrengthResponse,
)

RosterStateCode = Literal[
    "stable",
    "new",
    "incomplete",
    "stand_in",
    "unknown",
]


class TeamRosterStateResponse(BaseModel):
    code: RosterStateCode
    note: str


class TeamSummaryResponse(BaseModel):
    id: UUID
    name: str
    country: str | None
    region: str | None

    active_players_count: int
    team_strength_score: float
    roster_state: TeamRosterStateResponse


class TeamSummaryListResponse(BaseModel):
    items: list[TeamSummaryResponse]
    total: int


class TeamDashboardMapResponse(BaseModel):
    map_name: str | None

    total_matches: int
    wins: int
    losses: int
    win_rate: float

    ct_win_rate: float
    t_win_rate: float

    map_strength_score: float
    recent_form_score: float
    confidence_score: float
    confidence_level: str
    map_tier: str

    last_played_date: date | None
    days_since_last_played: int | None

    is_strong_map: bool
    is_weak_map: bool
    is_permaban_map: bool


class TeamDashboardResponse(BaseModel):
    id: UUID
    name: str
    country: str | None
    region: str | None
    liquipedia_url: str | None
    hltv_id: int | None

    roster_state: TeamRosterStateResponse
    roster: list[TeamRosterMemberResponse]
    strength: TeamStrengthResponse
    maps: list[TeamDashboardMapResponse]


class TeamComparisonSideResponse(BaseModel):
    team_id: UUID
    team_name: str

    active_players_count: int
    team_strength_score: float
    relative_strength_percent: float | None

    roster_state: TeamRosterStateResponse


class TeamRoleComparisonResponse(BaseModel):
    role: str

    team_a_score: float
    team_b_score: float

    team_a_players: list[str]
    team_b_players: list[str]

    advantage_team_name: str | None
    advantage_diff: float
    note: str


class TeamMapComparisonSideResponse(BaseModel):
    team_name: str
    total_matches: int
    win_rate: float
    map_strength_score: float
    confidence_score: float
    confidence_level: str
    map_tier: str


class TeamMapComparisonResponse(BaseModel):
    map_name: str | None

    team_a: TeamMapComparisonSideResponse
    team_b: TeamMapComparisonSideResponse

    team_a_relative_strength_percent: float | None
    team_b_relative_strength_percent: float | None

    advantage_team_name: str | None
    advantage_score: float
    matchup_confidence_level: str
    recommendation: str


class TeamHeadToHeadMapResponse(BaseModel):
    parse_run_id: UUID

    tournament_name: str | None
    match_date: date | None
    map_name: str | None
    map_number: int | None

    team_a_name: str
    team_b_name: str

    team_a_rounds: int
    team_b_rounds: int
    winner_team_name: str | None


class TeamComparisonDashboardResponse(BaseModel):
    team_a: TeamComparisonSideResponse
    team_b: TeamComparisonSideResponse

    strength_advantage_team_name: str | None
    strength_advantage_diff: float

    role_comparisons: list[TeamRoleComparisonResponse]
    map_comparisons: list[TeamMapComparisonResponse]
    recent_head_to_head_maps: list[TeamHeadToHeadMapResponse]

    summary_notes: list[str]