from datetime import date
from typing import Literal

from pydantic import BaseModel

from cs2eye.api.schemas.matches import MatchResponse, TournamentResponse


StructureType = Literal["single_elimination", "double_elimination", "swiss", "groups", "groups_playoff", "mixed", "unknown"]


class TournamentSummary(BaseModel):
    series_count: int
    map_count: int
    parsed_maps: int
    review_series: int
    missing_veto_series: int


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
