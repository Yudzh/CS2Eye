from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from cs2eye.api.schemas.match_analysis_context import BettingRestrictionsContext


MatchFormat = Literal["bo1", "bo3", "bo5", "unknown"]
MatchStage = Literal["group", "swiss", "round_of_32", "round_of_16", "quarterfinal", "semifinal", "final", "unknown"]
MatchEnvironment = Literal["lan", "online", "unknown"]
MatchResolution = Literal["resolved", "needs_review", "unresolved"]


class TournamentResponse(BaseModel):
    id: int; name: str; year: int; tier: str | None
    environment: MatchEnvironment; start_date: date | None; end_date: date | None
    structure_type: Literal["single_elimination", "double_elimination", "swiss", "groups", "groups_playoff", "mixed", "unknown"] = "unknown"


class MatchTeamResponse(BaseModel):
    id: int | None; name: str | None


class MatchScoreResponse(BaseModel):
    team_a: int; team_b: int


class MatchMapResponse(BaseModel):
    map_number: int; map_name: str | None; team_a_score: int | None; team_b_score: int | None
    winner_team_id: int | None; demo_file_id: int
    map_role: Literal["team_pick", "opponent_pick", "decider", "unknown"] = "unknown"
    picked_by_team_id: int | None = None
    parse_status: str = "pending"
    source_deleted_at: str | None = None
    source_available: bool = False

class MatchVetoActionResponse(BaseModel):
    id: int; order_index: int; team_id: int | None; team_name: str | None
    action: Literal["ban", "pick", "decider"]; map_name: str
    source: str; source_external_id: str | None


class MatchResponse(BaseModel):
    id: int; tournament: TournamentResponse | None; match_date: date
    format: MatchFormat; stage: MatchStage; environment: MatchEnvironment
    status: str; resolution_status: MatchResolution; is_playoff: bool; is_elimination: bool
    team_a: MatchTeamResponse; team_b: MatchTeamResponse; score: MatchScoreResponse
    winner_team_id: int | None; maps: list[MatchMapResponse]
    veto_data_status: Literal["not_available", "complete", "partial", "needs_review", "invalid"]
    veto_expected: bool
    veto: list[MatchVetoActionResponse]
    round_number: int | None = None; round_label: str | None = None
    group_name: str | None = None; bracket_section: Literal["main", "upper", "lower", "group", "swiss"] | None = None
    bracket_position: int | None = None; next_match_id: int | None = None
    next_match_slot: Literal["team_a", "team_b"] | None = None
    loser_next_match_id: int | None = None
    loser_next_match_slot: Literal["team_a", "team_b"] | None = None
    betting_restrictions: BettingRestrictionsContext = Field(
        default_factory=lambda: BettingRestrictionsContext(restricted=False),
    )


class MatchListResponse(BaseModel):
    total: int; items: list[MatchResponse]


class MatchCreateRequest(BaseModel):
    demo_file_ids: list[int] = Field(min_length=1, max_length=5)
    format: MatchFormat = "unknown"; stage: MatchStage = "unknown"
    environment: MatchEnvironment = "unknown"; resolution_status: MatchResolution = "resolved"


class MatchPatchRequest(BaseModel):
    format: MatchFormat | None = None; stage: MatchStage | None = None
    environment: MatchEnvironment | None = None; resolution_status: MatchResolution | None = None
    is_playoff: bool | None = None; is_elimination: bool | None = None
    tournament_id: int | None = None
    round_number: int | None = Field(None, ge=1); round_label: str | None = Field(None, max_length=160)
    group_name: str | None = Field(None, max_length=160)
    bracket_section: Literal["main", "upper", "lower", "group", "swiss"] | None = None
    bracket_position: int | None = Field(None, ge=1); next_match_id: int | None = None
    next_match_slot: Literal["team_a", "team_b"] | None = None
    loser_next_match_id: int | None = None
    loser_next_match_slot: Literal["team_a", "team_b"] | None = None


class MatchReorderRequest(BaseModel):
    demo_file_ids: list[int] = Field(min_length=1, max_length=5)


class MatchSplitRequest(BaseModel):
    demo_file_ids: list[int] | None = None

class MatchVetoActionRequest(BaseModel):
    order_index: int = Field(ge=1); team_id: int | None = None; team_name: str | None = None
    action: Literal["ban", "pick", "decider"]; map_name: str; source_external_id: str | None = None

class MatchVetoUpdateRequest(BaseModel):
    actions: list[MatchVetoActionRequest] | None = None
    text: str | None = None
    status: Literal["not_available", "complete", "partial", "needs_review", "invalid"] | None = None
    source_external_id: str | None = None


class MatchStatLineResponse(BaseModel):
    matches_played: int; matches_won: int; matches_lost: int; match_win_rate: float | None


class TeamMatchStatsResponse(BaseModel):
    team_id: int; aggregation_level: Literal["organization", "current_roster"]
    roster_id: int | None; all: MatchStatLineResponse
    by_format: dict[str, MatchStatLineResponse]; by_context: dict[str, MatchStatLineResponse]


class MatchBackfillResponse(BaseModel):
    candidate_groups: int; processed_groups: int; resolved_matches: int
    needs_review_matches: int; unresolved_matches: int; failed_groups: int
    errors: list[str]
