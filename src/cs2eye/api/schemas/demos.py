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


class DemoArtifactPrepareResponse(BaseModel):
    artifact_id: str
    stored_filename: str
    artifact_type: str
    prepared_dir: str
    demo_files: list[str]
    status: str


class DemoBasicStatsAnalyzeRequest(BaseModel):
    demo_file_path: str


class DemoPlayerDamageStats(BaseModel):
    player_name: str
    team_name: str | None
    total_damage: int
    rounds: int
    average_damage_per_round: float

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
    rounds: int
    players: list[DemoPlayerDamageStats]
    status: str
    bomb_rounds: list[DemoBombRoundStats]
