from uuid import UUID

from pydantic import BaseModel

from cs2eye.api.schemas.demos import DemoTeamMapMatchupItem


class BettingTeamStrengthResponse(BaseModel):
    team_id: UUID
    team_name: str

    active_players_count: int
    base_player_score: float

    roster_bonus: float
    roster_penalty: float

    team_strength_score: float

    missing_required_roles: list[str]
    notes: list[str]


class BettingTeamRoleComparisonResponse(BaseModel):
    role: str

    team_a_score: float
    team_b_score: float

    team_a_players: list[str]
    team_b_players: list[str]

    advantage_team_name: str | None
    advantage_diff: float

    note: str


class BettingTeamCompareResponse(BaseModel):
    team_a: BettingTeamStrengthResponse
    team_b: BettingTeamStrengthResponse

    strength_advantage_team_name: str | None
    strength_advantage_diff: float

    role_comparisons: list[BettingTeamRoleComparisonResponse]

    summary_notes: list[str]


class BettingDraftSignalResponse(BaseModel):
    edge_team_name: str | None
    edge_score: float

    bet_signal: str
    risk_level: str
    confidence_level: str

    explanation: str


class BettingPreMatchDraftResponse(BaseModel):
    team_a_name: str
    team_b_name: str
    map_name: str | None = None

    roster_comparison: BettingTeamCompareResponse
    map_comparisons: list[DemoTeamMapMatchupItem]

    draft_signal: BettingDraftSignalResponse
    notes: list[str]

    total_maps_compared: int