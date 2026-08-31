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
  key: string; raw_value: unknown; normalized_score: number | null;
  weight: number; effective_weight: number; impact: number;
  sample_size: number | null; confidence: number | null;
  reason: string | null; available: boolean;
  reference_value: number | null; reference_source: string | null;
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
  model_version: string; raw_score: number; reliability: number;
  confidence_adjustment: number; final_score: number;
  team_strength_raw_score: number; team_strength_reliability: number;
  team_strength_model_version: string;
}

export interface TeamDetail extends Team {
  strength: TeamStrength;
  leadership: Leadership;
  analyst_factors: AnalystFactor[];
  form_context: FormContext;
}
export interface FormContext {as_of:string;window_days:number;tournament_id:number|null;tournament_form_score:number|null;tournament_strength_of_schedule_score:number|null;tournament_reliability:number;recent_60d_adjusted_form_score:number|null;strength_of_schedule_score:number|null;performance_vs_expectation_score:number|null;recent_60d_reliability:number;tournament_matches_count:number;recent_60d_matches_count:number;top5_matches_60d:number;top10_matches_60d:number;top20_matches_60d:number;top30_matches_60d:number;close_series_count:number;upset_wins_count:number;strong_losses_count:number;performed_above_expectation_count:number;performed_below_expectation_count:number;status:"available"|"insufficient_data";tournament_status:"available"|"insufficient_data";cutoff_policy:string}
export type AnalystFactorType = "positive" | "negative";
export type AnalystEnvironment = "lan" | "online" | "any";
export type AnalystCategory = "overall"|"ct_defense"|"t_attack"|"tactics"|"veto"|"form"|"communication"|"roles"|"individual"|"teamplay"|"mental"|"coach"|"roster"|"other";
export interface AnalystFactor {id:number;team_id:number;team_name:string;factor_type:AnalystFactorType;text:string;category:AnalystCategory|null;map_name:string|null;environment:AnalystEnvironment;players:Array<{id:number;nickname:string}>;coach:{id:number;nickname:string}|null;valid_from:string|null;valid_until:string|null;is_active:boolean;status:"active"|"expired"|"inactive"|"scheduled";created_at:string;updated_at:string}
export interface AnalystFactorPayload {team_id:number;factor_type:AnalystFactorType;text:string;category:AnalystCategory|null;map_name:string|null;environment:AnalystEnvironment;player_ids:number[];coach_id:number|null;valid_from:string|null;valid_until:string|null;is_active:boolean}
export interface LeadershipFactor {key:string;label:string;raw_value:unknown;normalized_score:number|null;weight:number;effective_weight:number;impact:number;sample_size:number|null;confidence:number|null;reason:string|null;available:boolean}
export interface LeadershipScore {score:number;raw_score:number;reliability:number;model_version:string;management_residual:number|null;actual_performance:number|null;expected_performance:number|null;sample:{maps:number;available_factors:number;total_factors:number};factors:LeadershipFactor[]}
export interface Leadership {management_context:{roster_id:number|null;period_started_at:string|null;role_history_status:string};igl:(LeadershipScore&{player_id:number;name:string;player_strength:number|null;captain_strength:number|null;period:{started_at:string|null;ended_at:string|null;source:string}})|null;coach:(LeadershipScore&{id:number;name:string;roster_attribution_factor:number;tenure:{started_at:string|null;ended_at:string|null;source:string}})|null}

export interface TeamMapScope {
  maps_played: number; maps_won: number; maps_lost: number; map_win_rate: number | null;
  rounds_played: number; rounds_won: number; rounds_lost: number; round_win_rate: number | null;
  ct: { rounds_played: number; rounds_won: number; rounds_lost: number; win_rate: number | null };
  t: { rounds_played: number; rounds_won: number; rounds_lost: number; win_rate: number | null };
  bomb: BombStats;
  economy: EconomyStats | null;
  combat: TeamCombatStats | null;
  utility: UtilityStats | null;
  sample_size_score: number; sample_size_label: string;
  freshness_score: number; freshness_label: string;
  first_match_date: string | null; last_match_date: string | null;
}

export interface TeamCombatStats {
  opening: { kills: number; deaths: number; success_rate: number | null; conversion_rate: number | null; recovery_rate: number | null; ct_kills: number; ct_deaths: number; t_kills: number; t_deaths: number };
  trade: { trade_kills: number; deaths_traded: number; eligible_team_deaths: number; trade_rate: number | null };
  clutch: { opportunities: number; wins: number; win_rate: number | null; clutches_lost_to_opponent: number; breakdown: Record<string, {attempts: number; wins: number}> };
}
export interface UtilityStats {
  rounds_played: number; total_utility_thrown: number; utility_per_round: number | null;
  he_thrown: number; flash_thrown: number; smoke_thrown: number; fire_thrown: number;
  he_damage: number; fire_damage: number; utility_damage: number;
  he_damage_per_round: number | null; fire_damage_per_round: number | null; utility_damage_per_round: number | null;
  enemies_flashed: number; teammates_flashed: number; enemies_flashed_per_flash: number | null;
  flash_assists: number; flash_assists_per_round: number | null;
  ct: Record<string, number | null>; t: Record<string, number | null>;
}

export interface BombStats {
  t_rounds_played: number; plants: number; plant_rate: number | null;
  postplant_rounds: number; postplant_wins: number; postplant_losses: number; postplant_win_rate: number | null;
  retake_opportunities: number; retake_wins: number; retake_losses: number; retake_win_rate: number | null;
  explosions: number; defuses: number;
}

export interface EconomyMetric { rounds: number; wins: number; losses: number; win_rate: number | null }
export interface EconomyStats {
  pistol: EconomyMetric; first_pistol: EconomyMetric; second_pistol: EconomyMetric;
  both_pistols: EconomyMetric; conversion: EconomyMetric;
  post_pistol_vs_force: EconomyMetric; second_round_comeback: EconomyMetric;
  eco: EconomyMetric; force_buy: EconomyMetric; full_buy: EconomyMetric;
  anti_eco: EconomyMetric; full_buy_vs_full_buy: EconomyMetric;
  force_vs_full_buy: EconomyMetric;
  save: {rounds: number; players_saved: number; status: string};
}

export type MapStrengthStatus = "available" | "not_enough_data";
export type MapConfidenceLevel = "not_enough_data" | "low_confidence" | "medium_confidence" | "high_confidence";

export interface MapStrengthFactor {
  code: "overall_performance" | "recent_form" | "strong_opponents" | "side_strength" | "confidence_adjustment";
  label: string;
  score: number | null;
  configured_weight: number;
  effective_weight: number;
  impact: number;
  explanation: string;
}

export interface MapStrengthResult {
  status: MapStrengthStatus;
  map_strength_score: number | null;
  performance_score: number | null;
  confidence_score: number;
  confidence_level: MapConfidenceLevel;
  factors: MapStrengthFactor[];
  warnings: string[];
  model_version: string; raw_score: number | null; reliability: number;
  confidence_adjustment: number | null; final_score: number | null;
}

export interface TeamMapAggregate {
  map_name: string; all: TeamMapScope;
  recent: Record<"last_5" | "last_10" | "last_20", (TeamMapScope & { requested_window: number; actual_sample: number }) | null>;
  versus: Record<"top_15" | "top_16_30" | "tier_2_3", TeamMapScope | null>;
  strength: MapStrengthResult;
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

export type TeamH2HSliceStatus = "available" | "no_meetings" | "current_roster_unavailable" | "current_rosters_never_met" | "partial_data";
export type TeamH2HConfidenceLevel = "no_data" | "low" | "medium" | "high";
export type TeamH2HSampleLabel = "no_data" | "very_small" | "small" | "medium" | "sufficient";

export interface TeamH2HTeamMetrics {
  maps_won: number; map_win_rate: number | null; weighted_map_win_rate: number | null;
  rounds_won: number; round_win_rate: number | null; weighted_round_win_rate: number | null;
  performance_score: number | null; h2h_rating: number | null;
}

export interface TeamH2HMapBreakdown {
  map_name: string; maps_played: number; team_a_maps_won: number; team_b_maps_won: number;
  team_a_map_win_rate: number; team_b_map_win_rate: number;
  team_a_rounds_won: number; team_b_rounds_won: number;
  team_a_round_win_rate: number; team_b_round_win_rate: number;
  first_meeting_date: string; last_meeting_date: string; overtime_maps: number;
}

export interface TeamH2HRecentMap {
  demo_file_id: number; match_date: string; tournament: string; map_name: string;
  team_a_score: number; team_b_score: number; winner_team_id: number; went_to_overtime: boolean;
  team_a_roster_id: number | null; team_b_roster_id: number | null; recency_weight: number;
}

export interface TeamH2HFactor { code: string; score: number; weight: number; explanation: string }

export interface TeamH2HSlice {
  status: TeamH2HSliceStatus; candidate_maps_count: number; included_maps_count: number; excluded_maps_count: number;
  maps_played: number; effective_maps: number; sample_label: TeamH2HSampleLabel;
  confidence_score: number; confidence_level: TeamH2HConfidenceLevel;
  first_meeting_date: string | null; last_meeting_date: string | null;
  team_a: TeamH2HTeamMetrics; team_b: TeamH2HTeamMetrics;
  advantage_team_id: number | null; advantage_team_name: string | null; advantage_diff: number | null;
  advantage_level: "none" | "small" | "clear" | "strong";
  maps: TeamH2HMapBreakdown[]; recent_maps: TeamH2HRecentMap[]; factors: TeamH2HFactor[]; warnings: string[];
  series_played: number; team_a_series_won: number; team_b_series_won: number;
}

export interface TeamH2HPlayerExperience {
  player_id: number | null; nickname: string; maps_against_opponent: number; has_h2h_experience: boolean;
}

export interface TeamH2HLatestRosterOverlap {
  status: "available" | "unavailable"; latest_h2h_roster_id: number | null; current_roster_id: number | null;
  latest_roster_players_count: number; current_roster_players_count: number; retained_players_count: number;
  changed_players_count: number; retained_players: TeamH2HPlayerExperience[];
  new_current_players: TeamH2HPlayerExperience[]; former_players: TeamH2HPlayerExperience[];
}

export interface TeamH2HRosterContext {
  experience: {
    current_roster_id: number | null; current_players_count: number; players_with_h2h_experience_count: number;
    players_without_h2h_experience_count: number; experience_coverage_percent: number | null;
    average_maps_per_current_player: number | null; experience_data_status: "available" | "partial" | "unavailable";
    players: TeamH2HPlayerExperience[];
  };
  latest_roster_overlap: TeamH2HLatestRosterOverlap;
}

export interface TeamH2HComparison {
  status: string;
  team_a: { id: number; name: string; current_roster_id: number | null };
  team_b: { id: number; name: string; current_roster_id: number | null };
  organizations: TeamH2HSlice; current_rosters: TeamH2HSlice;
  roster_context: { team_a: TeamH2HRosterContext; team_b: TeamH2HRosterContext; history_applicability: "direct" | "high" | "medium" | "low" | "unknown" };
  insights: Array<{ code: string; text: string }>;
}

export type MatchFormat = "bo1" | "bo3" | "bo5" | "unknown";
export type MatchStage = "group" | "swiss" | "round_of_32" | "round_of_16" | "quarterfinal" | "semifinal" | "final" | "unknown";
export type MatchEnvironment = "lan" | "online" | "unknown";
export type MatchResolution = "resolved" | "needs_review" | "unresolved";
export type TournamentStructure = "single_elimination"|"double_elimination"|"swiss"|"groups"|"groups_playoff"|"mixed"|"unknown";
export interface MatchSeries {
  id: number; tournament: null | { id: number; name: string; year: number; tier: string | null; environment: MatchEnvironment; start_date: string | null; end_date: string | null; structure_type:TournamentStructure };
  match_date: string; format: MatchFormat; stage: MatchStage; environment: MatchEnvironment;
  status: string; resolution_status: MatchResolution; is_playoff: boolean; is_elimination: boolean;
  team_a: { id: number | null; name: string | null }; team_b: { id: number | null; name: string | null };
  score: { team_a: number; team_b: number }; winner_team_id: number | null;
  maps: Array<{ map_number: number; map_name: string | null; team_a_score: number | null; team_b_score: number | null; winner_team_id: number | null; demo_file_id: number; map_role: "team_pick"|"opponent_pick"|"decider"|"unknown"; picked_by_team_id:number|null; parse_status:string; source_deleted_at:string|null; source_available:boolean }>;
  veto_data_status: "not_available"|"complete"|"partial"|"needs_review"|"invalid";
  veto_expected: boolean;
  veto: VetoAction[];
  round_number:number|null;round_label:string|null;group_name:string|null;bracket_section:"main"|"upper"|"lower"|"group"|"swiss"|null;bracket_position:number|null;next_match_id:number|null;next_match_slot:"team_a"|"team_b"|null;loser_next_match_id?:number|null;loser_next_match_slot?:"team_a"|"team_b"|null;
  betting_restrictions?:BettingRestrictions;
}
export interface VetoAction { id?:number; order_index:number; team_id:number|null; team_name?:string|null; action:"ban"|"pick"|"decider"; map_name:string; source?:string; source_external_id?:string|null }
export interface VetoActionRate {count:number;rate:number|null}
export interface VetoActorScope {eligible_series:number;opening_ban:VetoActionRate;pick:VetoActionRate;closing_ban:VetoActionRate}
export interface VetoMap { map_name:string; active:boolean; eligible_series:number; veto_appearances:number; selected:VetoActionRate;opening_ban:VetoActionRate;closing_ban:VetoActionRate;when_first_actor:VetoActorScope;when_second_actor:VetoActorScope; ban:{count:number;rate:number|null;first_ban_count:number;first_ban_rate:number|null}; pick:{count:number;rate:number|null;first_pick_count:number;first_pick_rate:number|null;maps:number;wins:number;losses:number;win_rate:number|null}; opponent_pick:{count:number;rate:number|null;maps:number;wins:number;losses:number;win_rate:number|null}; decider:{count:number;rate:number|null;maps:number;wins:number;losses:number;win_rate:number|null}; is_likely_permaban:boolean;permaban_confidence:number;pick_preference_score:number|null }
export interface TeamVetoProfile { team_id:number;team_name:string;aggregation_level:"organization"|"current_roster";roster_id:number|null;sample:{series:number;complete_series:number};veto_confidence:number;denominator:string;maps:VetoMap[] }
export interface VetoComparison {team_a:TeamVetoProfile;team_b:TeamVetoProfile;maps:Array<{map_name:string;team_a:VetoMap;team_b:VetoMap;collision:"unknown"|"low"|"medium"|"high";availability:"unknown"|"likely_available"|"contested"|"likely_removed"}>;h2h:{series:number;maps:VetoMap[]}}
export interface CalculatedVetoFactor {key:string;label:string;raw_value:unknown;score:number|null;normalized_score:number|null;weight:number;effective_weight:number;impact:number;sample_size:number|null;confidence:number|null;reason:string|null;available:boolean}
export interface CalculatedVetoSide {matchup_map_score:number;calculated_pick_score:number;calculated_ban_score:number;matchup_confidence:number;pick_confidence:number;ban_confidence:number;matchup_factors:CalculatedVetoFactor[];pick_factors:CalculatedVetoFactor[];ban_factors:CalculatedVetoFactor[]}
export interface CalculatedVeto {calculated_veto_model_version:string;method:"exact_conditional_veto_tree";probability_semantics:"heuristic_estimate_not_calibrated";format:"bo3";first_actor:"team_a"|"team_b"|null;first_actor_assumption:"unknown_equal_50_50"|null;pool_size:number;expected_selected_maps:number;branch_probability_sum:number;team_a:{id:number;name:string};team_b:{id:number;name:string};opening_bans:{team_a:Array<{map:string;probability:number}>;team_b:Array<{map:string;probability:number}>};maps:Array<{map:string;active:boolean;rank:number;opening_ban_probability:number;opening_ban_survival_probability:number;pick_probability:number;pick_by_team_a_probability:number;pick_by_team_b_probability:number;closing_ban_probability:number;decider_probability:number;any_ban_probability:number;series_map_probability:number;confidence:number;components:{historical_selection:number;pick_pressure:number;ban_survival:number;map_matchup_quality:number};team_a_history:{selected_rate:number;pick_rate:number;ban_rate:number};team_b_history:{selected_rate:number;pick_rate:number;ban_rate:number};history_samples:{team_a:{organization:number;current_roster:number;recent:number};team_b:{organization:number;current_roster:number;recent:number}};team_a:CalculatedVetoSide;team_b:CalculatedVetoSide;collision_score:number;collision:"low"|"medium"|"high"}>}
export interface MatchupFactor {key:string;label:string;score:number|null;weight:number;effective_weight:number;impact:number;confidence:number|null;sample:number|null;reason:string|null;available:boolean}
export interface MatchupScore {model_version:string;score_semantics:"analytical_score_0_100_not_probability";analysis_mode:"pre_veto"|"post_veto";format:"bo1"|"bo3"|"bo5";as_of:string;historical_policy:string;team_a:{id:number;name:string;score:number;advantage:number};team_b:{id:number;name:string;score:number;advantage:number};raw_score:number;reliability:number;confidence_level:"low"|"medium"|"high";advantage:{team_id:number|null;team_name:string|null;level:"neutral"|"slight"|"moderate"|"strong"};factors:MatchupFactor[];maps:Array<{map:string;map_matchup_score:number;team_b_score:number;playability_weight:number;role:string;confidence:number;contribution:number}>;tactical:Record<string,unknown>&{score:number|null};veto:{basis:string;series_id:number|null;calculated_veto_model_version?:string};limitations:string[]}
export interface WinProbability {
  model_version:string|null;feature_schema_version?:string;trained_at?:string;
  model_status:"active"|"experimental"|"unavailable";quality_gate_passed:boolean;
  prediction_status:"available"|"insufficient_data"|"model_not_trained";
  team_a:{id:number;name?:string|null;probability:number|null};
  team_b:{id:number;name?:string|null;probability:number|null};
  confidence:number;
  basis?:{analysis_mode:"pre_veto"|"post_veto";veto:"calculated_veto"|"actual_veto";matchup_score:number};
  explanation?:{method:string;neutral_probability:number;predicted_probability:number;note:string;has_counterintuitive_factors:boolean;top_factors:Array<{key:string;label:string;feature_value:number;coefficient:number;impact_percentage_points:number;favors:"team_a"|"team_b"|"neutral";counterintuitive:boolean}>}|null;
  limitations:string[];
}

export type LLMSide="team_a"|"team_b"|"neutral";
export type LLMClaimCategory="overall_strength"|"recent_form"|"tournament_form"|"strength_of_schedule"|"performance_vs_expectation"|"roster"|"map_pool"|"veto"|"ct_side"|"t_side"|"economy"|"opening"|"trade"|"clutch"|"postplant"|"retake"|"leadership"|"h2h"|"ml_prediction"|"manual_context"|"data_quality"|"other";
export type LLMEvidenceKind="statistical"|"ml"|"deterministic"|"manual"|"mixed"|"data_quality"|null;
export interface LLMRosterPlayer{id:number|null;name:string;role:string|null}
export interface LLMTeamContext{id:number|null;name:string|null;rank:number|null;roster:{roster_id:number|null;players:LLMRosterPlayer[];coach:{id:number|null;name:string}|null;stability_score:number|null;reliability:number|null;sample_maps:number};team_strength:{score:number|null;reliability:number|null;sample_size:number;key_factors:Array<{factor_id:string;key:string;score:number|null;reliability:number|null}>};form:{tournament_form_score:number|null;tournament_matches:number;tournament_reliability:number|null;recent_60d_score:number|null;recent_60d_matches:number;recent_60d_reliability:number|null;strength_of_schedule_score:number|null;performance_vs_expectation_score:number|null;matches_vs_top_5:number;matches_vs_top_10:number;matches_vs_top_30:number};leadership:{igl_score:number|null;coach_score:number|null;reliability:number|null;sample_size:number}}
export interface LLMRecentSeries{evidence_id:string;date:string|null;tournament:string|null;opponent:{id:number|null;name:string|null;rank:number|null};result:"win"|"loss"|null;series_score:string|null;expected_win_probability:number|null;performance_vs_expectation:number|null;current_tournament:boolean|null;reliability:number|null}
export interface HEKillByMapPrediction{map:string;probability:number;confidence:"low"|"medium"|"high";team_a_sample:number;team_b_sample:number}
export type BettingRestrictionRule="navi_no_match_winner_bets"|"group_stage_no_match_winner_bets";
export interface BettingRestrictionItem{rule:BettingRestrictionRule;message:string}
export interface BettingRestrictions{restricted:boolean;rule:BettingRestrictionRule|null;message:string|null;restrictions?:BettingRestrictionItem[]}
export interface HEKillQualityMetrics{predictions_count:number;brier_score:number|null;avg_predicted_probability:number|null;actual_he_kill_rate:number|null}
export interface HEKillBacktestReport{model_version:string;confidence_model_version?:string;metrics:HEKillQualityMetrics;calibration:Array<HEKillQualityMetrics&{bucket:string;lower_bound:number;upper_bound:number}>;by_map:Array<HEKillQualityMetrics&{map:string}>;by_confidence:Array<HEKillQualityMetrics&{confidence:"low"|"medium"|"high"}>;predictions:Array<{series_id:number;map:string;as_of:string;team_a:{id:number;name:string|null};team_b:{id:number;name:string|null};predicted_probability:number;confidence:"low"|"medium"|"high";team_a_sample:number;team_b_sample:number;actual_he_kill:boolean}>}
export interface LLMMatchAnalysisContext{schema_version:"match_analysis_context.v1";generated_at:string;as_of:string;analysis_mode:"pre_match"|"post_match";match:{id:number|null;date:string|null;format:"bo1"|"bo3"|"bo5"|null;environment:"lan"|"online"|null;stage:string|null;is_playoff:boolean|null;is_elimination:boolean|null;tournament:{id:number|null;name:string|null;tier:string|null};round_number:number|null;round_label:string|null;section:string|null};teams:{team_a:LLMTeamContext;team_b:LLMTeamContext};recent_series_evidence:{team_a:LLMRecentSeries[];team_b:LLMRecentSeries[]};prediction:{source_type:"ml_prediction";status:string;model_version:string|null;quality_gate_passed:boolean|null;team_a_probability:number|null;team_b_probability:number|null;confidence:number|null;top_model_drivers:Array<{driver_id:string;key:string;favored_team:LLMSide|null;importance:number|null;reliability:number|null}>};matchup:{source_type:"deterministic_analytics";model_version:string|null;team_a_score:number|null;team_b_score:number|null;reliability:number|null;factors:Array<{factor_id:string;key:string;team_a_score:number|null;team_b_score:number|null;reliability:number|null;sample_size:number|null}>};veto:{source_type:"deterministic_analytics";basis:"calculated_veto";model_version:string|null;likely_maps:Array<{map:string;series_probability:number|null;confidence:number|null;likely_role:string}>};map_matchups:Array<{map:string;relevance:number|null;team_a:{map_strength:number|null;reliability:number|null;sample_maps:number};team_b:{map_strength:number|null;reliability:number|null;sample_maps:number};matchup_score_team_a:number|null;key_edges:Array<{evidence_id:string;metric:string;favored_team:"team_a"|"team_b";strength:string;reliability:number|null}>}>;h2h:{preferred_scope:string;history_applicability:string;organizations:Record<string,unknown>;current_rosters:Record<string,unknown>};manual_context:{source_type:"manual_analyst_note";team_a:LLMManualNote[];team_b:LLMManualNote[]};secondary_bets?:{he_kill_by_map:HEKillByMapPrediction[]};betting_restrictions?:BettingRestrictions;data_quality:{overall_status:"available"|"partial"|"weak"|"insufficient";limitations:string[];missing_sections:string[];warnings:string[]}}
export interface LLMManualNote{note_id:string;polarity:string;category:string|null;players:string[];coach:string|null;map:string|null;environment:string|null;text:string}
export interface LLMAnalysisClaim{claim_id:string;side:LLMSide;category:LLMClaimCategory;importance:"high"|"medium"|"low";statement:string;evidence_refs:string[];evidence_kind:LLMEvidenceKind}
export interface LLMAnalysisRisk{risk_id:string;severity:"high"|"medium"|"low";category:LLMClaimCategory;statement:string;evidence_refs:string[];evidence_kind:LLMEvidenceKind}
export interface LLMDataLimitation{limitation_id:string;severity:"high"|"medium"|"low";statement:string;evidence_refs:string[];evidence_kind:LLMEvidenceKind}
export interface MatchLLMAnalysisV1{schema_version:"match_llm_analysis.v1";context_schema_version:"match_analysis_context.v1";analysis_status:"complete"|"limited"|"insufficient_data";conclusion:{favored_team:"team_a"|"team_b"|"none";advantage:"none"|"small"|"moderate"|"clear";confidence:"high"|"medium"|"low"|"insufficient";reasoning_basis:"ml_prediction"};key_advantages:LLMAnalysisClaim[];counter_arguments:LLMAnalysisClaim[];contradictions:Array<{contradiction_id:string;importance:"high"|"medium"|"low";description:string;evidence_refs:string[]}>;risks:LLMAnalysisRisk[];data_limitations:LLMDataLimitation[];summary:string}
export interface MatchLLMAnalysisV2{schema_version:"match_llm_analysis.v2";explanation_plan_version:"match_explanation_plan.v1";summary:string;advantage_texts:Record<string,string>;counter_argument_texts:Record<string,string>;contradiction_texts:Record<string,string>;risk_texts:Record<string,string>;limitation_texts:Record<string,string>}
export interface MatchLLMAnalysisV3{schema_version:"match_llm_analysis.v3";explanation_plan_version:"match_explanation_plan.v2";expected_winner_text?:string|null;conclusion_text:string;form_text:string;maps_text:string;teamplay_text:string;manual_text:string}
export type MatchLLMAnalysis=MatchLLMAnalysisV1|MatchLLMAnalysisV2|MatchLLMAnalysisV3;
export interface MatchExplanationSignal{signal_id:string;side:"team_a"|"team_b";category:LLMClaimCategory;direction:"supports_favorite"|"against_favorite";strength:"small"|"moderate"|"strong";importance:"high"|"medium"|"low";reliability:number;sample_size:number|null;evidence_refs:string[];source_kind:"statistical"|"ml"|"deterministic"|"manual"}
export interface MatchExplanationPlan{schema_version:"match_explanation_plan.v1";context_schema_version:"match_analysis_context.v1";status:"complete"|"limited"|"insufficient_data";conclusion:{favored_team:"team_a"|"team_b"|"none";advantage:"none"|"small"|"moderate"|"clear";confidence:"high"|"medium"|"low"|"insufficient";ml_probability_team_a:number|null;ml_probability_team_b:number|null};advantages:MatchExplanationSignal[];counter_arguments:MatchExplanationSignal[];contradictions:Array<{contradiction_id:string;category:string;importance:"high"|"medium"|"low";left_ref:string;right_ref:string;left_side:"team_a"|"team_b";right_side:"team_a"|"team_b"}>;risks:Array<{risk_id:string;category:LLMClaimCategory;severity:"high"|"medium"|"low";evidence_refs:string[]}>;limitations:Array<{limitation_id:string;category:LLMClaimCategory;severity:"high"|"medium"|"low";evidence_refs:string[]}>}
export interface MatchExplanationPlanV2{schema_version:"match_explanation_plan.v2";context_schema_version:"match_analysis_context.v1";expected_winner?:{team_id:number;team_name:string;win_probability:number}|null;conclusion:{team_a_name:string;team_b_name:string;favored_team:"team_a"|"team_b"|"none";advantage:"none"|"small"|"moderate"|"clear";confidence:"high"|"medium"|"low"|"insufficient";ml_probability_team_a:number|null;ml_probability_team_b:number|null;internal_statistics_disclaimer:string};form:Record<string,unknown>;maps:Record<string,unknown>;teamplay:Record<string,unknown>;manual_context:Record<string,unknown>}
export interface MatchLLMRuntime{provider:"ollama"|"none";model:string;prompt_version:string;attempts:number;input_tokens:number|null;output_tokens:number|null;provider_response_id:string|null;schema_valid:boolean;business_valid:boolean;grounding_valid:boolean;repair_attempted:boolean;grounding_error_codes:string[]}
export interface MatchLLMAnalysisRun{analysis_run_id:number;source_run_id:number|null;status:"pending"|"completed"|"failed"|"skipped_insufficient_data";context:LLMMatchAnalysisContext;explanation_plan?:MatchExplanationPlan|MatchExplanationPlanV2|null;analysis:MatchLLMAnalysis|null;runtime:MatchLLMRuntime;error_code:string|null;error_message:string|null;validation_error_codes:string[];created_at:string;completed_at:string|null}
export interface MatchLLMHistoryItem{id:number;source_run_id:number|null;created_at:string;status:MatchLLMAnalysisRun["status"];provider:string|null;model:string|null;prompt_version:string;as_of:string;analysis_status:string|null;favored_team:string|null;confidence:string|null}
export interface MatchLLMGenerateRequest{team_a_id:number;team_b_id:number;as_of:string;match_id?:number;tournament_id?:number;match_format?:"bo1"|"bo3"|"bo5";analysis_mode:"pre_match";language:"ru"}
export interface MLModelArtifact {id:number;model_version:string;feature_schema_version:string;trained_at:string;trained:boolean;quality_gate_passed:boolean;active:boolean;forced_active:boolean;model_status:"active"|"experimental"|"inactive";training_series:number;validation_series:number;test_series:number;eligible_series:number;metrics:{brier_score?:number;log_loss?:number};baselines:Record<string,{brier_score?:number;log_loss?:number}>}
export interface MLModelsStatus {active:MLModelArtifact|null;artifacts:MLModelArtifact[]}
export interface MatchListResponse { total: number; items: MatchSeries[] }
export interface PredictionHistoryMetric{correct:number;total:number;accuracy:number|null}
export interface PredictionHistoryPrediction{team_a_value:number|null;team_b_value:number|null;predicted_winner_id:number|null;predicted_winner:string|null;correct:boolean|null;probability:boolean}
export type PredictionConflictType="none"|"incomplete"|"ts_matchup_vs_ml"|"ts_ml_vs_matchup"|"matchup_ml_vs_ts"|"all_three_different";
export interface PredictionConflict{type:PredictionConflictType;strength:number|null;strong:boolean;majority_winner_id:number|null;majority_winner:string|null;dissent_winner_id:number|null;dissent_winner:string|null;dissenting_prediction:"team_strength"|"matchup"|"ml"|null}
export interface PredictionConflictMetric{total:number;majority_correct:number;dissent_correct:number;majority_accuracy:number|null;dissent_accuracy:number|null}
export interface PredictionHistoryItem{id:number;match_id:number;tournament_id:number|null;tournament:string|null;match_date:string;as_of:string;created_at:string;source:"live"|"retrospective";team_a:{id:number;name:string|null};team_b:{id:number;name:string|null};actual_winner_id:number|null;actual_winner:string|null;completed:boolean;team_strength:PredictionHistoryPrediction;matchup:PredictionHistoryPrediction;ml:PredictionHistoryPrediction;consensus:{winner_id:number|null;winner:string|null;votes:number;total:number;correct:boolean|null};conflict:PredictionConflict}
export interface PredictionHistoryResponse{items:PredictionHistoryItem[];statistics:{team_strength:PredictionHistoryMetric;matchup:PredictionHistoryMetric;ml:PredictionHistoryMetric;consensus_3_3:PredictionHistoryMetric;conflicts:Record<"ts_matchup_vs_ml"|"ts_ml_vs_matchup"|"matchup_ml_vs_ts",PredictionConflictMetric>;strong_conflict_threshold:number};tournaments:Array<{id:number;name:string}>}
export interface MatchStatLine { matches_played: number; matches_won: number; matches_lost: number; match_win_rate: number | null }
export interface TeamMatchStats { team_id: number; aggregation_level: "organization" | "current_roster"; roster_id: number | null; all: MatchStatLine; by_format: Record<"bo1" | "bo3" | "bo5", MatchStatLine>; by_context: Record<"lan" | "online" | "playoff" | "elimination" | "final", MatchStatLine> }
export interface MatchBackfillResult { candidate_groups: number; processed_groups: number; resolved_matches: number; needs_review_matches: number; unresolved_matches: number; failed_groups: number; errors: string[] }
export interface TournamentSummary {series_count:number;map_count:number;parsed_maps:number;review_series:number;missing_veto_series:number;participant_count:number;scheduled_series:number}
export interface TournamentListItem {id:number;name:string;year:number;tier:string|null;environment:MatchEnvironment;start_date:string|null;end_date:string|null;structure_type:TournamentStructure;summary:TournamentSummary}
export interface TournamentListResponse {total:number;items:TournamentListItem[]}
export interface TournamentProblem {match_id:number;code:string;message:string}
export interface TournamentView {tournament:Omit<TournamentListItem,"summary">;summary:TournamentSummary;matches:MatchSeries[];stages:string[];bracket_links:Array<{from_match_id:number;to_match_id:number;source:"manual"|"inferred"}>;problems:TournamentProblem[];participants:Array<{team_id:number;name:string;seed:number|null}>}
export interface TournamentPredictionMatch {id:number;source_match_id:number|null;round_number:number|null;round_label:string|null;stage:MatchStage;bracket_section:MatchSeries["bracket_section"];bracket_position:number|null;format:MatchFormat;team_a:{id:number|null;name:string|null};team_b:{id:number|null;name:string|null};team_a_probability:number|null;team_b_probability:number|null;team_a_score:number|null;team_b_score:number|null;predicted_winner_id:number|null;predicted_winner_name:string|null;confidence:number|null;reliability:number|null;prediction_type:"actual_match"|"projected_match";prediction_basis:"win_probability"|"matchup_score";status:"available"|"comparison_fallback"|"insufficient_data"|"model_not_trained"|"actual_result";model_version:string|null;created_at:string;invalidated_at:string|null}
export interface TournamentPredictions {tournament_id:number;prediction_run_id:number;generated_at:string;model_version:string|null;model_status?:"active"|"experimental"|null;quality_gate_passed?:boolean|null;status:string;outdated:boolean;matches:TournamentPredictionMatch[]}
export interface TournamentCreate {name:string;year:number;tier:string|null;environment:"lan"|"online";start_date:string;end_date:string;structure_type:TournamentStructure;team_ids:number[];matches:Array<{team_a_id:number|null;team_b_id:number|null;match_date:string;format:"bo1"|"bo3"|"bo5";stage:MatchStage;round_number:number|null;round_label:string|null;group:string|null;bracket_section:MatchSeries["bracket_section"];bracket_position:number|null}>}

export interface TeamMapComparisonSide {
  maps_played: number; maps_won: number; maps_lost: number; map_win_rate: number | null;
  map_strength_score: number | null; confidence_score: number;
  confidence_level: MapConfidenceLevel; status: MapStrengthStatus;
  bomb: BombStats;
  economy: EconomyStats | null;
  combat: TeamCombatStats | null;
  utility: UtilityStats | null;
}

export interface TeamMapComparisonItem {
  map_name: string;
  team_a: TeamMapComparisonSide | null;
  team_b: TeamMapComparisonSide | null;
  comparison_status: "comparable" | "team_a_no_data" | "team_b_no_data" | "both_no_data" | "team_a_not_enough_data" | "team_b_not_enough_data" | "both_not_enough_data";
  advantage_team_id: number | null;
  advantage_team_name: string | null;
  advantage_diff: number | null;
  advantage_level: "none" | "small" | "clear" | "strong" | null;
}

export interface TeamMapComparisonResponse {
  aggregation_level: "organization" | "current_roster";
  team_a: { id: number; name: string; rank: number | null; roster_id: number | null };
  team_b: { id: number; name: string; rank: number | null; roster_id: number | null };
  status: string;
  maps: TeamMapComparisonItem[];
  summary: { team_a_advantage_maps: number; team_b_advantage_maps: number; close_maps: number; not_comparable_maps: number };
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
  leadership: Leadership;
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
  round_swing_comparison: {scope:string;current_roster:boolean;team_a:RosterSwingProfile;team_b:RosterSwingProfile;overall:{team_a:RosterSwingProfile;team_b:RosterSwingProfile};per_map:Record<string,{team_a:RosterSwingProfile;team_b:RosterSwingProfile}>;round_win_model_version:string|null;round_swing_model_version:string;trained_at:string|null};
  analyst_context:{team_a:{relevant:AnalystFactor[];all_active:AnalystFactor[]};team_b:{relevant:AnalystFactor[];all_active:AnalystFactor[]}};
  team_a_form_context:FormContext;
  team_b_form_context:FormContext;
}

export interface RosterSwingProfile {status:string;source:string;avg_swing?:number;top2_swing?:number;bottom2_swing?:number;ct_swing?:number|null;t_swing?:number|null;opening_swing?:number|null;clutch_swing?:number|null;confidence:number;sample:{players:number;rounds:number}}


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
  player_strength_raw_score: number | null;
  player_strength_reliability: number | null;
  player_strength_model_version: string | null;
  igl: Leadership["igl"];
  captain_strength: number|null;
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
    model_version: string; raw_score: number; reliability: number;
    confidence_adjustment: number; final_score: number;
    normalization_source: string;
    factors: Array<{key: string; label: string; raw_value: unknown;
      normalized_score: number | null; weight: number; effective_weight: number;
      impact: number; sample_size: number | null; confidence: number | null;
      reason: string | null; available: boolean}>;
  } | null;
  stats_synced_at: string | null;
  source_updated_at: string | null;
  teams: PlayerTeam[];
  combat: { overall: Record<string, number | null> | null; recent_10: Record<string, number | null> | null; top_15: Record<string, number | null> | null; top_16_30: Record<string, number | null> | null; maps: Record<string, Record<string, number | null> | null> };
  utility: { overall: UtilityStats | null; recent_5: UtilityStats | null; recent_10: UtilityStats | null; recent_20: UtilityStats | null; top_15: UtilityStats | null; top_16_30: UtilityStats | null; maps: Record<string, UtilityStats | null> };
  round_swing: SwingScope & {status:string;overall:SwingScope|null;maps:Record<string,SwingScope|null>;rank_scopes:Record<string,SwingScope|null>;recent:Record<string,SwingScope|null>;model?:{round_win_model_version:string|null;round_swing_model_version:string;trained_at:string|null}};
}

export interface SwingScope {score?:number|null;raw_per_round?:number;adjusted_per_round?:number;confidence?:number;rounds?:number;ct?:number|null;t?:number|null;opening?:number|null;trade?:number|null;clutch?:number|null;postplant?:number|null;retake?:number|null;total_swing?:number;positive_swing?:number;negative_swing?:number}


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
  parse_job_id: string | null;
  parse_job_status: string | null;
}

export interface DemoListFile {
  id: number;
  filename: string;
  storage_path: string;
  file_size_bytes: number;
  sha256: string;
  uploaded_at: string;
  updated_at: string;
  source_deleted_at: string | null;
  source_available: boolean;
  parse_status: "pending" | "processing" | "success" | "failed";
  map_name: string | null;
  team_a_name: string | null;
  team_a_score: number | null;
  team_b_name: string | null;
  team_b_score: number | null;
  winner_team_name: string | null;
  metadata_status: DemoMetadataStatus | null;
  round_data_status: RoundDataStatus | null;
  bomb_data_status: RoundDataStatus | null;
  economy_data_status: RoundDataStatus | null;
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
  bomb_data_status: RoundDataStatus;
  economy_data_status: RoundDataStatus;
  combat_data_status: RoundDataStatus;
  utility_data_status: RoundDataStatus;
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
  bomb_planted: boolean; bomb_defused: boolean; bomb_exploded: boolean;
  is_pistol_round: boolean; pistol_round_number: number | null;
  team_a_equipment_value: number | null; team_b_equipment_value: number | null;
  team_a_economy: "eco" | "force_buy" | "full_buy" | "unknown";
  team_b_economy: "eco" | "force_buy" | "full_buy" | "unknown";
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
export interface DemoTeamBombStat extends BombStats { team_id: number | null; team_name: string }
export interface DemoBombStatsResponse { demo_file_id: number; map_name: string | null; bomb_data_status: RoundDataStatus; teams: DemoTeamBombStat[] }
export interface DemoTeamEconomyStat extends Omit<EconomyStats, "save"> {
  team_id: number | null; team_name: string; save_rounds: number;
  players_saved: number; save_data_status: string;
}
export interface DemoEconomyStatsResponse {
  demo_file_id: number; map_name: string | null; economy_data_status: RoundDataStatus;
  teams: DemoTeamEconomyStat[];
}
export interface DemoCombatStatsResponse {
  demo_file_id: number; map_name: string | null; combat_data_status: RoundDataStatus;
  teams: Array<{team_id: number | null; team_name: string; [key: string]: unknown}>;
  players: Array<{player_id: number | null; nickname: string; team_name: string | null; [key: string]: unknown}>;
}
export interface DemoUtilityStatsResponse {
  demo_file_id: number; map_name: string | null; utility_data_status: RoundDataStatus;
  teams: Array<UtilityStats & {team_id: number | null; team_name: string}>;
  players: Array<UtilityStats & {player_id: number | null; nickname: string; team_name: string | null}>;
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
  combat: Record<string, number | null> | null;
  utility: UtilityStats | null;
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

export interface DemoParseJob {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  processed_files: number;
  total_files: number;
  parsed_count: number;
  skipped_count: number;
  failed_count: number;
  current_filename: string | null;
  error: string | null;
  result: DemoParseResponse | null;
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
