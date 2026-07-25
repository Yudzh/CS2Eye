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


export interface TeamParticipant {
  id: number;
  bo3_id: number;
  bo3_slug: string;
  nickname: string;
  image_url: string | null;
  country_code: string | null;
  country_name: string | null;
  participant_type: "player" | "substitute" | "coach";
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
