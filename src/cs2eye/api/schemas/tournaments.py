from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from cs2eye.api.schemas.matches import MatchResponse, TournamentResponse


StructureType = Literal["single_elimination", "double_elimination", "swiss", "groups", "groups_playoff", "mixed", "unknown"]


class TournamentSummary(BaseModel):
    series_count: int
    map_count: int
    parsed_maps: int
    review_series: int
    missing_veto_series: int
    participant_count: int = 0
    scheduled_series: int = 0

class TournamentParticipant(BaseModel):
    team_id: int
    name: str
    seed: int | None = None

class ScheduledMatchCreate(BaseModel):
    team_a_id: int | None = None
    team_b_id: int | None = None
    match_date: date
    format: Literal["bo1", "bo3", "bo5"]
    stage: Literal["group", "swiss", "round_of_32", "round_of_16", "quarterfinal", "semifinal", "final", "unknown"] = "unknown"
    round_number: int | None = Field(None, ge=1)
    round_label: str | None = Field(None, max_length=160)
    group_name: str | None = Field(None, max_length=160, alias="group")
    bracket_section: Literal["main", "upper", "lower", "group", "swiss"] | None = None
    bracket_position: int | None = Field(None, ge=1)

class TournamentScheduledMatchCreate(ScheduledMatchCreate):
    pass

class TournamentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    year: int = Field(ge=2000, le=2100)
    tier: str | None = Field(None, max_length=32)
    environment: Literal["lan", "online"]
    start_date: date
    end_date: date
    structure_type: StructureType
    team_ids: list[int] = Field(min_length=1)
    matches: list[ScheduledMatchCreate] = []

    @model_validator(mode="after")
    def validate_request(self):
        if self.start_date > self.end_date: raise ValueError("Дата начала турнира не может быть позже даты окончания.")
        if len(self.team_ids) != len(set(self.team_ids)): raise ValueError("Команду нельзя добавить в participants дважды.")
        return self


class TournamentListItem(TournamentResponse):
    summary: TournamentSummary


class TournamentListResponse(BaseModel):
    total: int
    items: list[TournamentListItem]


class TournamentPatchRequest(BaseModel):
    structure_type: StructureType | None = None
    tier: str | None = None
    environment: Literal["lan", "online", "unknown"] | None = None
    start_date: date | None = None
    end_date: date | None = None


class TournamentProblem(BaseModel):
    match_id: int
    code: str
    message: str


class BracketLink(BaseModel):
    from_match_id: int
    to_match_id: int
    source: Literal["manual", "inferred"]


class TournamentViewResponse(BaseModel):
    tournament: TournamentResponse
    summary: TournamentSummary
    matches: list[MatchResponse]
    stages: list[str]
    bracket_links: list[BracketLink]
    problems: list[TournamentProblem]
    participants: list[TournamentParticipant] = []
