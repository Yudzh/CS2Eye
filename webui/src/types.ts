export type RosterStateCode =
  | "stable"
  | "new"
  | "incomplete"
  | "stand_in"
  | "unknown";

export type TeamStrengthFactorKind =
  | "base"
  | "bonus"
  | "penalty"
  | "info";


export interface TeamStrengthFactor {
  code: string;
  label: string;

  kind: TeamStrengthFactorKind;

  value: number;
  explanation: string;

  players: string[];
}


export interface TeamRosterState {
  code: RosterStateCode;
  note: string;
}


export interface TeamSummary {
  id: string;
  name: string;

  country: string | null;
  region: string | null;

  active_players_count: number;
  team_strength_score: number;

  roster_state: TeamRosterState;
}


export interface TeamSummaryListResponse {
  items: TeamSummary[];
  total: number;
}


export interface TeamRosterMember {
  roster_member_id: string;
  player_id: string;

  nickname: string;
  real_name: string | null;
  country: string | null;

  status: string;
  role: string | null;

  joined_at: string | null;
  left_at: string | null;

  current_rating: number | null;
  player_strength_score: number;

  source_name: string | null;
  source_url: string | null;
  source_confidence: number;

  notes: string | null;
}


export interface TeamStrength {
  team_id: string;
  team_name: string;

  active_players_count: number;
  base_player_score: number;

  roster_bonus: number;
  roster_penalty: number;

  team_strength_score: number;

  missing_required_roles: string[];
  notes: string[];
  total_adjustment: number;
    score_before_limits: number;

    calculation: string;

    factors: TeamStrengthFactor[];
}


export interface TeamDashboardMap {
  map_name: string | null;

  total_matches: number;
  wins: number;
  losses: number;
  win_rate: number;

  ct_win_rate: number;
  t_win_rate: number;

  map_strength_score: number;
  recent_form_score: number;

  confidence_score: number;
  confidence_level: string;
  map_tier: string;

  last_played_date: string | null;
  days_since_last_played: number | null;

  is_strong_map: boolean;
  is_weak_map: boolean;
  is_permaban_map: boolean;
}


export interface TeamDashboard {
  id: string;
  name: string;

  country: string | null;
  region: string | null;

  liquipedia_url: string | null;
  hltv_id: number | null;

  roster_state: TeamRosterState;

  roster: TeamRosterMember[];
  strength: TeamStrength;
  maps: TeamDashboardMap[];
}


export interface TeamComparisonSide {
  team_id: string;
  team_name: string;

  active_players_count: number;
  team_strength_score: number;

  relative_strength_percent: number | null;

  roster_state: TeamRosterState;
}


export interface TeamRoleComparison {
  role: string;

  team_a_score: number;
  team_b_score: number;

  team_a_players: string[];
  team_b_players: string[];

  advantage_team_name: string | null;
  advantage_diff: number;

  note: string;
}


export interface TeamMapComparisonSide {
  team_name: string;

  total_matches: number;
  win_rate: number;

  map_strength_score: number;
  confidence_score: number;

  confidence_level: string;
  map_tier: string;
}


export interface TeamMapComparison {
  map_name: string | null;

  team_a: TeamMapComparisonSide;
  team_b: TeamMapComparisonSide;

  team_a_relative_strength_percent: number | null;
  team_b_relative_strength_percent: number | null;

  advantage_team_name: string | null;
  advantage_score: number;

  matchup_confidence_level: string;
  recommendation: string;
}


export interface TeamHeadToHeadMap {
  parse_run_id: string;

  tournament_name: string | null;
  match_date: string | null;
  map_name: string | null;
  map_number: number | null;

  team_a_name: string;
  team_b_name: string;

  team_a_rounds: number;
  team_b_rounds: number;

  winner_team_name: string | null;
}


export interface TeamComparisonDashboard {
  team_a: TeamComparisonSide;
  team_b: TeamComparisonSide;

  strength_advantage_team_name: string | null;
  strength_advantage_diff: number;

  role_comparisons: TeamRoleComparison[];
  map_comparisons: TeamMapComparison[];

  recent_head_to_head_maps: TeamHeadToHeadMap[];

  summary_notes: string[];
}

export type TeamRoleCode =
  | "igl"
  | "awper"
  | "rifler"
  | "entry_frag"
  | "lurk"
  | "anchor_support"
  | "coach";


export type RosterMemberStatus =
  | "active"
  | "coach";


export interface TeamRoleOption {
  value: TeamRoleCode;
  label: string;

  allowed_statuses:
    RosterMemberStatus[];
}


export interface LiquipediaRoleAssignment {
  nickname: string;
  role: TeamRoleCode;
}


export interface LiquipediaRosterPlayerPreview {
  nickname: string;
  real_name: string | null;
  country: string | null;

  status: RosterMemberStatus;
  role: TeamRoleCode | null;

  joined_at: string | null;
  left_at: string | null;

  liquipedia_url: string | null;
  source_url: string;

  source_confidence: number;
  notes: string | null;
}


export interface LiquipediaTeamPreview {
  team_name: string;
  liquipedia_url: string;

  players:
    LiquipediaRosterPlayerPreview[];

  warnings: string[];
  role_options: TeamRoleOption[];

  total_players: number;
  active_players_count: number;
}


export interface LiquipediaSavedTeam {
  id: string;
  name: string;

  country: string | null;
  region: string | null;

  liquipedia_url: string | null;
  hltv_id: number | null;

  roster: TeamRosterMember[];
  strength: TeamStrength;
}


export interface LiquipediaTeamResponse {
  saved: boolean;
  override_roster: boolean;

  preview: LiquipediaTeamPreview;

  team: LiquipediaSavedTeam | null;
}


export interface LiquipediaTeamRequest {
  team_page: string;
  team_name: string | null;

  override_roster: boolean;

  role_assignments:
    LiquipediaRoleAssignment[];
}


export interface AdminTeam {
  id: string;
  name: string;

  country: string | null;
  region: string | null;

  liquipedia_url: string | null;
  hltv_id: number | null;

  roster: TeamRosterMember[];
  strength: TeamStrength;
}


export interface AdminTeamListResponse {
  items: AdminTeam[];
  total: number;
}


export interface ManualRosterPlayerUpdate {
  nickname: string;
  delete: 0 | 1;

  role: TeamRoleCode | null;

  real_name: string | null;
  country: string | null;

  joined_at: string | null;
  left_at: string | null;

  liquipedia_url: string | null;
  hltv_id: number | null;

  current_rating: number | null;

  player_strength_score:
    number | null;

  notes: string | null;
}


export interface ManualRosterUpdateRequest {
  players:
    ManualRosterPlayerUpdate[];
}


export interface TeamDeleteResponse {
  deleted: boolean;
  team_name: string;
}