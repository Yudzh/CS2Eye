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

class DemoArtifactPrepareResponse(BaseModel):
    artifact_id: str
    stored_filename: str
    artifact_type: str
    prepared_dir: str
    demo_files: list[PreparedDemoFile]
    status: str


class DemoBasicStatsAnalyzeRequest(BaseModel):
    demo_file_path: str
    map_name: str | None = None
    team_a_name: str | None = None
    team_b_name: str | None = None

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

class DemoBombAnalysisMeeting(BaseModel):
    parse_run_id: UUID
    demo_file_path: str
    map_name: str | None
    team_a_name: str | None
    team_b_name: str | None
    rounds_count: int | None
    exploded_bombs: int
    defused_bombs: int


class DemoBombAnalysisResponse(BaseModel):
    map_name: str
    team_a_name: str | None
    team_b_name: str | None
    matches_count: int
    average_exploded_bombs_per_map: float
    average_defused_bombs_per_map: float
    meetings: list[DemoBombAnalysisMeeting]