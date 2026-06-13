from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class DemoListItem(BaseModel):
    id: str
    filename: str
    status: str


class DemoListResponse(BaseModel):
    items: list[DemoListItem] = Field(default_factory=list)
    total: int = 0


class DemoUploadResponse(DemoListItem):
    stored_filename: str
    file_path: str
    artifact_type: str


class HltvDemoResolveRequest(BaseModel):
    match_url: str

class HltvDemoResolveResponse(HltvDemoResolveRequest):
    download_url: str
    archive_url: str | None = None

class DemoArtifactPrepareRequest(BaseModel):
    stored_filename: str

class PreparedDemoFile(BaseModel):
    demo_file_path: str
    file_name: str
    artifact_id: str | None
    detected_team_a_name: str | None
    detected_team_b_name: str | None
    detected_map_name: str | None
    metadata_detected_from_filename: bool
    detected_map_number: int | None

class DemoArtifactPrepareResponse(BaseModel):
    artifact_id: str
    stored_filename: str
    artifact_type: str
    prepared_dir: str
    demo_files: list[PreparedDemoFile]
    status: str


class DemoBasicStatsAnalyzeRequest(BaseModel):
    demo_file_path: str

    tournament_name: str | None = None
    match_date: date | None = None

    map_name: str | None = None
    team_a_name: str | None = None
    team_b_name: str | None = None
    map_number: int | None = None

class DemoPreparedPathAnalyzeRequest(BaseModel):
    demo_file_path: str
    tournament_name: str
    match_date: date

class DemoBombRoundStats(BaseModel):
    round_number: int
    planter_name: str | None
    planter_team_name: str | None
    defuser_name: str | None
    defuser_team_name: str | None
    outcome: str
    plant_tick: int | None
    defuse_tick: int | None
    explosion_tick: int | None

class DemoBombRoundStatsResponse(BaseModel):
    parse_run_id: UUID
    items: list[DemoBombRoundStats]
    total: int

class DemoBasicStatsAnalyzeResponse(BaseModel):
    parse_run_id: UUID
    demo_file_path: str
    map_name: str | None
    team_a_name: str | None
    team_b_name: str | None
    rounds: int
    status: str
    bomb_rounds: list[DemoBombRoundStats]
    map_number: int | None = None

class DemoBombAnalysisMap(BaseModel):
    map_name: str | None
    matches_count: int

    exploded_bombs: int
    defused_bombs: int

    average_exploded_bombs_per_map: float
    average_defused_bombs_per_map: float


class DemoBombAnalysisMeeting(BaseModel):
    parse_run_id: UUID
    demo_file_path: str

    tournament_name: str | None
    match_date: date | None

    map_name: str | None
    map_number: int | None = None

    team_a_name: str | None
    team_b_name: str | None

    rounds_count: int | None

    exploded_bombs: int
    defused_bombs: int


class DemoBombAnalysisResponse(BaseModel):
    map_name: str | None = None
    team_a_name: str | None = None
    team_b_name: str | None = None

    maps: list[DemoBombAnalysisMap]
    recent_meetings: list[DemoBombAnalysisMeeting]


class DemoUploadAnalyzeItem(BaseModel):
    parse_run_id: UUID | None = None
    demo_file_path: str
    file_name: str

    detected_team_a_name: str | None = None
    detected_team_b_name: str | None = None
    detected_map_number: int | None = None
    detected_map_name: str | None = None

    rounds: int | None = None
    status: str
    error_message: str | None = None


class DemoUploadAnalyzeResponse(BaseModel):
    artifact_id: str
    stored_filename: str
    artifact_type: str
    raw_file_path: str
    prepared_dir: str

    tournament_name: str
    match_date: date

    total_demo_files: int
    analyzed_count: int
    failed_count: int

    items: list[DemoUploadAnalyzeItem]


class DemoLocalPathImportRequest(BaseModel):
    path: str
    tournament_name: str
    match_date: date
    replace_existing: bool = True


class DemoLocalPathImportItem(BaseModel):
    parse_run_id: UUID | None = None
    demo_file_path: str
    file_name: str

    detected_team_a_name: str | None = None
    detected_team_b_name: str | None = None
    detected_map_number: int | None = None
    detected_map_name: str | None = None

    rounds: int | None = None
    status: str
    error_message: str | None = None


class DemoLocalPathImportResponse(BaseModel):
    source_path: str
    tournament_name: str
    match_date: date

    total_demo_files: int
    analyzed_count: int
    failed_count: int

    items: list[DemoLocalPathImportItem]


class DemoParseDataClearResponse(BaseModel):
    status: str
    message: str