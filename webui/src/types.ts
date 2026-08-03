export interface Team {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  name: string;
  logo_url: string | null;
  country_code: string | null;
  country_name: string | null;
  region: string | null;
  current_rank: number | null;
  current_points: string | number | null;
  rank_change: number | null;
  ranking_date: string | null;
  is_analytics_active: boolean;
  roster_synced_at: string | null;
  roster: TeamParticipant[];
}

export interface TeamStrengthFactor {
  code: string;
  label: string;
  kind: "base" | "bonus" | "penalty" | "info";
  value: number;
  explanation: string;
  players: string[];
}

export interface TeamStrength {
  active_players_count: number;
  base_player_score: number;
  roster_bonus: number;
  roster_penalty: number;
  total_adjustment: number;
  score_before_limits: number;
  team_strength_score: number;
  calculation: string;
  missing_required_roles: string[];
  factors: TeamStrengthFactor[];
  notes: string[];
}

export interface TeamDetail extends Team {
  strength: TeamStrength;
}

export interface TeamMapScope {
  maps_played: number; maps_won: number; maps_lost: number; map_win_rate: number | null;
  rounds_played: number; rounds_won: number; rounds_lost: number; round_win_rate: number | null;
  ct: { rounds_played: number; rounds_won: number; rounds_lost: number; win_rate: number | null };
  t: { rounds_played: number; rounds_won: number; rounds_lost: number; win_rate: number | null };
  sample_size_score: number; sample_size_label: string;
  freshness_score: number; freshness_label: string;
  first_match_date: string | null; last_match_date: string | null;
}

export interface TeamMapAggregate {
  map_name: string; all: TeamMapScope;
  recent: Record<"last_5" | "last_10" | "last_20", (TeamMapScope & { requested_window: number; actual_sample: number }) | null>;
  versus: Record<"top_15" | "top_16_30" | "tier_2_3", TeamMapScope | null>;
}

export interface TeamMapsResponse {
  team: { id: number; name: string; rank: number | null };
  aggregation_level: "organization" | "current_roster";
  roster_id: number | null;
  status: string;
  roster_sample: { maps_played: number; first_match_date: string | null; last_match_date: string | null } | null;
  maps: TeamMapAggregate[];
}

export interface TeamMapDetail extends TeamMapAggregate {
  aggregation_level: "organization" | "current_roster";
  roster_id: number | null;
  recent_matches: Array<{
    demo_file_id: number; match_date: string | null; opponent_team_name: string | null;
    opponent_rank: number | null; opponent_rank_group: string;
    score_for: number; score_against: number; result: "win" | "loss";
    ct_rounds_won: number; ct_rounds_played: number;
    t_rounds_won: number; t_rounds_played: number;
  }>;
}

export interface CurrentRosterComparison {
  status: string; met?: boolean; reason?: string;
  team_a: { id: number; name: string; current_roster_id: number | null; players: Array<{id: number; name: string; role: string | null}> };
  team_b: { id: number; name: string; current_roster_id: number | null; players: Array<{id: number; name: string; role: string | null}> };
  head_to_head: null | { maps_played: number; team_a_maps_won: number; team_b_maps_won: number; team_a_rounds_won: number; team_b_rounds_won: number; first_meeting_date: string | null; last_meeting_date: string | null };
  maps: Array<{map_name: string; maps_played: number; team_a_maps_won: number; team_b_maps_won: number}>;
  recent_maps: Array<{demo_file_id: number; match_date: string; tournament: string; map_name: string; team_a_score: number; team_b_score: number; winner_team_id: number; went_to_overtime: boolean}>;
}

export interface TeamComparisonPlayer {
  id: number;
  nickname: string;
  image_url: string | null;
  role: TeamParticipant["role"];
  bo3_rating: string | number | null;
  bo3_avg_rating: string | number | null;
  player_strength: number | null;
  internal_rating: string | number | null;
  internal_rating_version: string | null;
  internal_rating_top15: string | number | null;
  internal_rating_top16_30: string | number | null;
  effective_player_strength: number;
  strength_is_fallback: boolean;
}

export interface TeamComparisonSide {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  name: string;
  logo_url: string | null;
  country_code: string | null;
  country_name: string | null;
  region: string | null;
  current_rank: number | null;
  current_points: string | number | null;
  rank_change: number | null;
  ranking_date: string | null;
  roster_synced_at: string | null;
  active_players_count: number;
  roster: TeamComparisonPlayer[];
  coaches: TeamComparisonPlayer[];
  strength: TeamStrength;
  relative_strength_percent: number | null;
}

export interface TeamRoleComparison {
  role: string;
  team_a_score: number | null;
  team_b_score: number | null;
  team_a_players: TeamComparisonPlayer[];
  team_b_players: TeamComparisonPlayer[];
  advantage_team_id: number | null;
  advantage_team_name: string | null;
  advantage_diff: number | null;
  note: string;
}

export interface TeamComparison {
  team_a: TeamComparisonSide;
  team_b: TeamComparisonSide;
  strength_advantage_team_id: number | null;
  strength_advantage_team_name: string | null;
  strength_advantage_diff: number;
  ranking: {
    rank_advantage_team_id: number | null;
    rank_advantage_team_name: string | null;
    rank_difference: number | null;
    points_advantage_team_id: number | null;
    points_advantage_team_name: string | null;
    points_difference: string | number | null;
  };
  role_comparisons: TeamRoleComparison[];
  summary_notes: string[];
}


export interface TeamParticipant {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  nickname: string;
  image_url: string | null;
  country_code: string | null;
  country_name: string | null;
  participant_type: "player" | "substitute" | "coach";
  role: "igl" | "awper" | "entry_frag" | "lurk" | "anchor_support" | "rifler" | null;
  is_active: boolean;
  joined_at: string | null;
  left_at: string | null;
  player_strength: number | null;
  bo3_rating: string | number | null;
  bo3_avg_rating: string | number | null;
  internal_rating: string | number | null;
  internal_rating_maps_count: number;
  internal_rating_rounds_count: number;
  internal_rating_version: string | null;
  internal_rating_top15: string | number | null;
  internal_rating_top15_maps_count: number;
  internal_rating_top15_rounds_count: number;
  internal_rating_top16_30: string | number | null;
  internal_rating_top16_30_maps_count: number;
  internal_rating_top16_30_rounds_count: number;
}

export interface PlayerTeam {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  name: string;
  logo_url: string | null;
  is_active: boolean;
  participant_type: string;
}

export interface StrengthFactor {
  metric: string;
  value: number;
  impact: number;
  direction: "positive" | "negative" | "neutral";
  explanation: string;
}

export interface Player {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  nickname: string;
  first_name: string | null;
  last_name: string | null;
  image_url: string | null;
  country_code: string | null;
  country_name: string | null;
  bo3_rating: string | number | null;
  bo3_avg_rating: string | number | null;
  player_strength: number | null;
  steam_id: string | null;
  internal_rating: string | number | null;
  internal_rating_maps_count: number;
  internal_rating_rounds_count: number;
  internal_rating_updated_at: string | null;
  internal_rating_version: string | null;
  internal_rating_top15: string | number | null;
  internal_rating_top15_maps_count: number;
  internal_rating_top15_rounds_count: number;
  internal_rating_top16_30: string | number | null;
  internal_rating_top16_30_maps_count: number;
  internal_rating_top16_30_rounds_count: number;
  strength_breakdown: {
    baseline: number;
    formula: string;
    factors: StrengthFactor[];
  } | null;
  stats_synced_at: string | null;
  source_updated_at: string | null;
  teams: PlayerTeam[];
}


export interface RankingRun {
  id: number;
  status: "running" | "succeeded" | "failed";
  source: string;
  source_url: string;
  started_at: string;
  finished_at: string | null;
  ranking_date: string | null;
  teams_received: number;
  teams_activated: number;
  teams_deactivated: number;
  player_profiles_updated: number;
  player_profiles_failed: number;
  player_profile_failures: PlayerProfileFailure[];
  error_message: string | null;
}

export interface PlayerProfileFailure {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  nickname: string;
  error: string;
}


export interface ProbeTeam {
  rank: number;
  name: string;
  bo3_id: number;
  bo3_slug: string;
  points: string | number;
  rank_change: number | null;
  region: string | null;
  roster_size: number;
}


export interface ProbeResult {
  ranking_date: string;
  teams_received: number;
  teams: ProbeTeam[];
}

export type DemoUploadStatus = "created" | "replaced" | "unchanged" | "failed";

export interface DemoUploadFileResult {
  id: number | null;
  filename: string;
  status: DemoUploadStatus;
  storage_path: string | null;
  file_size_bytes: number | null;
  sha256: string | null;
  error?: string | null;
}

export interface DemoUploadResponse {
  tournament_name: string;
  tournament_slug: string;
  match_date: string;
  total_files: number;
  created_count: number;
  replaced_count: number;
  unchanged_count: number;
  failed_count: number;
  files: DemoUploadFileResult[];
}

export interface DemoListFile {
  id: number;
  filename: string;
  storage_path: string;
  file_size_bytes: number;
  sha256: string;
  uploaded_at: string;
  updated_at: string;
  parse_status: "pending" | "processing" | "success" | "failed";
  map_name: string | null;
  team_a_name: string | null;
  team_a_score: number | null;
  team_b_name: string | null;
  team_b_score: number | null;
  winner_team_name: string | null;
  metadata_status: DemoMetadataStatus | null;
  round_data_status: RoundDataStatus | null;
}

export type DemoMetadataStatus = "complete" | "partial" | "needs_review" | "invalid";
export type RoundDataStatus = "not_parsed" | "complete" | "partial" | "needs_review" | "invalid";

export interface DemoMapResult {
  demo_file_id: number;
  map_name: string | null;
  team_a: { id: number | null; name: string | null; score: number | null };
  team_b: { id: number | null; name: string | null; score: number | null };
  winner: { id: number | null; name: string | null } | null;
  rounds_count: number | null;
  went_to_overtime: boolean | null;
  result_source: "demo_parser" | "manual_override" | "mixed" | "unknown";
  metadata_status: DemoMetadataStatus;
  issues: string[];
  round_data_status: RoundDataStatus;
  rounds_parsed_count: number;
  rounds_expected_count: number | null;
  rounds_consistent: boolean;
}

export interface DemoRound {
  round_number: number; phase: "regulation" | "overtime"; half: string;
  team_a_side: "CT" | "T" | "unknown"; team_b_side: "CT" | "T" | "unknown";
  winner_team_id: number | null; winner_team_name: string | null; winner_side: "CT" | "T" | "unknown";
  end_reason: string; team_a_score_before: number | null; team_b_score_before: number | null;
  team_a_score_after: number | null; team_b_score_after: number | null;
  started_at_tick: number | null; ended_at_tick: number | null; duration_seconds: string | number | null;
}

export interface DemoRoundsResponse {
  demo_file_id: number; round_data_status: RoundDataStatus; total: number;
  page: number; page_size: number; items: DemoRound[];
}

export interface SideSummary { rounds_played: number; rounds_won: number; rounds_lost: number | null; win_rate: string | number | null }
export interface DemoTeamSideStat {
  team_id: number | null; team_name: string; ct: SideSummary; t: SideSummary;
  first_half: SideSummary; second_half: SideSummary; overtime: SideSummary; total: SideSummary;
}
export interface DemoSideStatsResponse {
  demo_file_id: number; map_name: string | null; round_data_status: RoundDataStatus; teams: DemoTeamSideStat[];
}

export interface DemoMapResultPatch {
  map_name: string | null;
  team_a_id: number | null;
  team_a_name: string | null;
  team_a_score: number | null;
  team_b_id: number | null;
  team_b_name: string | null;
  team_b_score: number | null;
}

export interface DemoMapOption { code: string; title: string; demo_names: string[] }

export interface DemoParseFileResult {
  demo_file_id: number;
  filename: string;
  status: "parsed" | "skipped" | "failed";
  players_found: number;
  players_linked: number;
  players_unlinked: number;
  error: string | null;
  unlinked_players: Array<{
    nickname: string;
    steam_id: string | null;
    team_name: string | null;
    demo_filename: string;
  }>;
  diagnostics: string[];
}

export interface DemoPlayerStat {
  player_id: number | null;
  steam_id: string | null;
  nickname: string;
  demo_team_id: number | null;
  demo_team_name: string | null;
  opponent_team_id: number | null;
  opponent_team_name: string | null;
  opponent_rank: number | null;
  opponent_rank_group: "top_15" | "top_16_30" | "outside_top_30" | "unknown";
  opponent_rank_source: "historical_snapshot" | "current_fallback" | "unknown";
  opponent_rank_snapshot_date: string | null;
}

export interface DemoRankReclassifyResponse {
  demo_files_found: number;
  player_stats_checked: number;
  updated_count: number;
  unchanged_count: number;
  failed_count: number;
  players_recalculated: number;
  failures: Array<{ demo_file_id: number; error: string }>;
}

export interface DemoPlayerStatsResponse {
  demo_file_id: number;
  filename: string;
  parse_status: string;
  players: DemoPlayerStat[];
}

export interface DemoParseResponse {
  tournament_name: string;
  year: number;
  total_files: number;
  parsed_count: number;
  skipped_count: number;
  failed_count: number;
  players_recalculated: number;
  files: DemoParseFileResult[];
}

export interface DemoListResponse {
  tournament_name: string;
  tournament_slug: string;
  year: number;
  total_files: number;
  dates: Array<{ match_date: string; files: DemoListFile[] }>;
}

export interface DemoTournamentOption {
  name: string;
  slug: string;
}
