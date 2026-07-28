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

export interface TeamComparisonPlayer {
  id: number;
  nickname: string;
  image_url: string | null;
  role: TeamParticipant["role"];
  bo3_rating: string | number | null;
  player_strength: number | null;
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
  player_strength: number | null;
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
