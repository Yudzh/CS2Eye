from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


MatchFormat = Literal["bo1", "bo3", "bo5", "unknown"]
MatchStage = Literal["group", "swiss", "round_of_32", "round_of_16", "quarterfinal", "semifinal", "final", "unknown"]
MatchEnvironment = Literal["lan", "online", "unknown"]
MatchResolution = Literal["resolved", "needs_review", "unresolved"]


class TournamentResponse(BaseModel):
    id: int; name: str; year: int; tier: str | None
    environment: MatchEnvironment; start_date: date | None; end_date: date | None


class MatchTeamResponse(BaseModel):
    id: int | None; name: str | None


class MatchScoreResponse(BaseModel):
    team_a: int; team_b: int


class MatchMapResponse(BaseModel):
    map_number: int; map_name: str | None; team_a_score: int | None; team_b_score: int | None
    winner_team_id: int | None; demo_file_id: int


class MatchResponse(BaseModel):
    id: int; tournament: TournamentResponse | None; match_date: date
    format: MatchFormat; stage: MatchStage; environment: MatchEnvironment
    status: str; resolution_status: MatchResolution; is_playoff: bool; is_elimination: bool
    team_a: MatchTeamResponse; team_b: MatchTeamResponse; score: MatchScoreResponse
    winner_team_id: int | None; maps: list[MatchMapResponse]


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


class MatchReorderRequest(BaseModel):
    demo_file_ids: list[int] = Field(min_length=1, max_length=5)


class MatchSplitRequest(BaseModel):
    demo_file_ids: list[int] | None = None


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
