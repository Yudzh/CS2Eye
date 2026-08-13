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
    parse_job_id: str | None = None
    parse_job_status: str | None = None


class DemoListFile(BaseModel):
    id: int
    filename: str
    storage_path: str
    file_size_bytes: int
    sha256: str
    uploaded_at: datetime
    updated_at: datetime
    parse_status: str = "pending"
    map_name: str | None = None
    team_a_name: str | None = None
    team_a_score: int | None = None
    team_b_name: str | None = None
    team_b_score: int | None = None
    winner_team_name: str | None = None
    metadata_status: str | None = None
    round_data_status: str | None = None
    bomb_data_status: str | None = None
    economy_data_status: str | None = None
    utility_data_status: str | None = None


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


class DemoParseJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    processed_files: int
    total_files: int
    parsed_count: int
    skipped_count: int
    failed_count: int
    current_filename: str | None
    error: str | None
    result: DemoParseResponse | None


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
    opponent_rank_source: Literal[
        "historical_snapshot", "current_fallback", "unknown",
    ]
    opponent_rank_snapshot_date: date | None
    combat: dict | None = None
    utility: dict | None = None


class DemoPlayerStatsResponse(BaseModel):
    demo_file_id: int
    filename: str
    parse_status: str
    players: list[DemoPlayerStatResponse]


class DemoMapTeamResponse(BaseModel):
    id: int | None
    name: str | None
    score: int | None = None


class DemoMapWinnerResponse(BaseModel):
    id: int | None
    name: str | None


class DemoMapResultResponse(BaseModel):
    demo_file_id: int
    map_name: str | None
    team_a: DemoMapTeamResponse
    team_b: DemoMapTeamResponse
    winner: DemoMapWinnerResponse | None
    rounds_count: int | None
    went_to_overtime: bool | None
    result_source: str
    metadata_status: str
    issues: list[str] = Field(default_factory=list)
    round_data_status: str
    bomb_data_status: str
    economy_data_status: str
    combat_data_status: str
    utility_data_status: str
    rounds_parsed_count: int
    rounds_expected_count: int | None
    rounds_consistent: bool


class DemoRoundResponse(BaseModel):
    round_number: int
    phase: str
    half: str
    team_a_side: str
    team_b_side: str
    winner_team_id: int | None
    winner_team_name: str | None
    winner_side: str
    end_reason: str
    team_a_score_before: int | None
    team_b_score_before: int | None
    team_a_score_after: int | None
    team_b_score_after: int | None
    started_at_tick: int | None
    ended_at_tick: int | None
    duration_seconds: Decimal | None
    bomb_planted: bool
    bomb_defused: bool
    bomb_exploded: bool
    is_pistol_round: bool
    pistol_round_number: int | None
    team_a_equipment_value: int | None
    team_b_equipment_value: int | None
    team_a_economy: str
    team_b_economy: str


class DemoRoundsResponse(BaseModel):
    demo_file_id: int
    round_data_status: str
    total: int
    page: int
    page_size: int
    items: list[DemoRoundResponse]


class SideSummary(BaseModel):
    rounds_played: int
    rounds_won: int
    rounds_lost: int | None = None
    win_rate: Decimal | None = None


class DemoTeamSideStatResponse(BaseModel):
    team_id: int | None
    team_name: str
    ct: SideSummary
    t: SideSummary
    first_half: SideSummary
    second_half: SideSummary
    overtime: SideSummary
    total: SideSummary


class DemoSideStatsResponse(BaseModel):
    demo_file_id: int
    map_name: str | None
    round_data_status: str
    teams: list[DemoTeamSideStatResponse]


class DemoTeamBombStatResponse(BaseModel):
    team_id: int | None
    team_name: str
    t_rounds_played: int
    plants: int
    plant_rate: Decimal | None
    postplant_rounds: int
    postplant_wins: int
    postplant_losses: int
    postplant_win_rate: Decimal | None
    retake_opportunities: int
    retake_wins: int
    retake_losses: int
    retake_win_rate: Decimal | None
    explosions: int
    defuses: int


class DemoBombStatsResponse(BaseModel):
    demo_file_id: int
    map_name: str | None
    bomb_data_status: str
    teams: list[DemoTeamBombStatResponse]


class EconomyMetricResponse(BaseModel):
    rounds: int
    wins: int
    losses: int
    win_rate: Decimal | None


class DemoTeamEconomyStatResponse(BaseModel):
    team_id: int | None
    team_name: str
    pistol: EconomyMetricResponse
    first_pistol: EconomyMetricResponse
    second_pistol: EconomyMetricResponse
    both_pistols: EconomyMetricResponse
    conversion: EconomyMetricResponse
    post_pistol_vs_force: EconomyMetricResponse
    second_round_comeback: EconomyMetricResponse
    eco: EconomyMetricResponse
    force_buy: EconomyMetricResponse
    full_buy: EconomyMetricResponse
    anti_eco: EconomyMetricResponse
    full_buy_vs_full_buy: EconomyMetricResponse
    force_vs_full_buy: EconomyMetricResponse
    save_rounds: int
    players_saved: int
    save_data_status: str


class DemoEconomyStatsResponse(BaseModel):
    demo_file_id: int
    map_name: str | None
    economy_data_status: str
    teams: list[DemoTeamEconomyStatResponse]


class DemoCombatStatsResponse(BaseModel):
    demo_file_id: int
    map_name: str | None
    combat_data_status: str
    teams: list[dict]
    players: list[dict]


class DemoUtilityStatsResponse(BaseModel):
    demo_file_id: int
    map_name: str | None
    utility_data_status: str
    teams: list[dict]
    players: list[dict]


class DemoMapResultPatch(BaseModel):
    map_name: str | None = None
    team_a_id: int | None = None
    team_a_name: str | None = None
    team_a_score: int | None = Field(default=None, ge=0)
    team_b_id: int | None = None
    team_b_name: str | None = None
    team_b_score: int | None = Field(default=None, ge=0)


class DemoMapOption(BaseModel):
    code: str
    title: str
    demo_names: list[str]


class DemoMapsResponse(BaseModel):
    items: list[DemoMapOption]


class DemoRankReclassifyRequest(BaseModel):
    tournament_name: str
    year: int
    only_unknown_or_fallback: bool = True


class DemoRankReclassifyResponse(BaseModel):
    demo_files_found: int
    player_stats_checked: int
    updated_count: int
    unchanged_count: int
    failed_count: int
    players_recalculated: int
    failures: list[dict[str, str | int]] = Field(default_factory=list)
