from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DemoUploadFileResult(BaseModel):
    id: int | None = None
    filename: str
    status: Literal["created", "replaced", "unchanged", "failed"]
    storage_path: str | None = None
    file_size_bytes: int | None = None
    sha256: str | None = None
    error: str | None = None


class DemoUploadResponse(BaseModel):
    tournament_name: str
    tournament_slug: str
    match_date: date
    total_files: int
    created_count: int
    replaced_count: int
    unchanged_count: int
    failed_count: int
    files: list[DemoUploadFileResult]


class DemoListFile(BaseModel):
    id: int
    filename: str
    storage_path: str
    file_size_bytes: int
    sha256: str
    uploaded_at: datetime
    updated_at: datetime
    parse_status: str = "pending"


class DemoDateGroup(BaseModel):
    match_date: date
    files: list[DemoListFile]


class DemoListResponse(BaseModel):
    tournament_name: str
    tournament_slug: str
    year: int
    total_files: int
    dates: list[DemoDateGroup]


class DemoTournamentOption(BaseModel):
    name: str
    slug: str


class DemoParseRequest(BaseModel):
    tournament_name: str
    year: int
    replace_existing: bool = False


class DemoParseFileResult(BaseModel):
    demo_file_id: int
    filename: str
    status: Literal["parsed", "skipped", "failed"]
    players_found: int = 0
    players_linked: int = 0
    players_unlinked: int = 0
    error: str | None = None
    unlinked_players: list[dict[str, str | None]] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class DemoParseResponse(BaseModel):
    tournament_name: str
    year: int
    total_files: int
    parsed_count: int
    skipped_count: int
    failed_count: int
    players_recalculated: int
    files: list[DemoParseFileResult]


class DemoPlayerStatResponse(BaseModel):
    player_id: int | None
    steam_id: str | None
    nickname: str
    team_name: str | None
    rounds_played: int
    kills: int
    deaths: int
    assists: int
    total_damage: int
    adr: Decimal
    kast_rounds: int
    kast_percent: Decimal
    internal_rating: Decimal
    internal_rating_version: str
    demo_team_id: int | None
    demo_team_name: str | None
    opponent_team_id: int | None
    opponent_team_name: str | None
    opponent_rank: int | None
    opponent_rank_group: str


class DemoPlayerStatsResponse(BaseModel):
    demo_file_id: int
    filename: str
    parse_status: str
    players: list[DemoPlayerStatResponse]
