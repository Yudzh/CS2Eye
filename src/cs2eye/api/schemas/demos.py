from datetime import date, datetime
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

class DemoParseRunListItem(BaseModel):
    id: UUID

    demo_file_name: str | None
    demo_file_path: str

    tournament_name: str | None
    match_date: date | None

    map_name: str | None
    map_number: int | None

    team_a_name: str | None
    team_b_name: str | None

    status: str
    rounds_count: int | None
    error_message: str | None

    started_at: datetime | None
    finished_at: datetime | None


class DemoParseRunListResponse(BaseModel):
    items: list[DemoParseRunListItem]
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


class DemoTeamMapRecentMatch(BaseModel):
    parse_run_id: UUID

    tournament_name: str | None
    match_date: date | None

    map_name: str | None
    team_name: str
    opponent_name: str | None

    rounds_won: int
    rounds_lost: int
    won: bool


class DemoTeamMapStatsItem(BaseModel):
    team_name: str
    map_name: str | None

    total_matches_on_map: int
    wins_on_map: int
    losses_on_map: int
    win_rate_on_map: float

    rounds_won_total: int
    rounds_lost_total: int
    avg_round_diff: float
    avg_rounds_won_per_map: float
    avg_rounds_lost_per_map: float

    win_rate_last_5_maps: float
    win_rate_last_10_maps: float
    win_rate_last_20_maps: float
    current_win_streak_on_map: int
    current_lose_streak_on_map: int
    last_played_date_on_map: date | None
    days_since_last_played_map: int | None

    win_rate_30_days: float
    win_rate_60_days: float
    win_rate_90_days: float
    matches_30_days: int
    matches_60_days: int
    matches_90_days: int

    ct_rounds_played: int
    ct_rounds_won: int
    ct_win_rate: float

    t_rounds_played: int
    t_rounds_won: int
    t_win_rate: float

    avg_bomb_plants_per_map: float
    avg_bomb_explosions_per_map: float
    avg_bomb_defuses_per_map: float

    map_sample_size_score: float
    recent_form_score: float
    map_strength_score: float
    map_confidence_score: float
    map_confidence_level: str
    map_tier: str

    is_strong_map: bool
    is_weak_map: bool
    is_permaban_map: bool

    recent_matches: list[DemoTeamMapRecentMatch]


class DemoTeamMapStatsResponse(BaseModel):
    team_name: str | None = None
    map_name: str | None = None
    items: list[DemoTeamMapStatsItem]
    total: int

class DemoTeamMapMatchupTeamStats(BaseModel):
    team_name: str
    map_name: str | None

    total_matches_on_map: int
    win_rate_on_map: float

    ct_win_rate: float
    t_win_rate: float

    avg_bomb_plants_per_map: float
    avg_bomb_explosions_per_map: float
    avg_bomb_defuses_per_map: float

    map_strength_score: float
    map_confidence_score: float
    map_confidence_level: str
    map_tier: str


class DemoTeamMapMatchupItem(BaseModel):
    map_name: str | None

    team_a: DemoTeamMapMatchupTeamStats
    team_b: DemoTeamMapMatchupTeamStats

    advantage_team_name: str | None
    advantage_score: float
    matchup_confidence_level: str
    recommendation: str


class DemoTeamMapMatchupResponse(BaseModel):
    team_a_name: str
    team_b_name: str
    map_name: str | None = None

    items: list[DemoTeamMapMatchupItem]
    total: int


class DemoRoundStats(BaseModel):
    round_number: int

    winner_team_name: str | None
    winner_side: str | None

    ct_team_name: str | None
    t_team_name: str | None

    reason: str | None


class DemoRoundStatsResponse(BaseModel):
    parse_run_id: UUID
    items: list[DemoRoundStats]
    total: int