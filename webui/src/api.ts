import type {
  ProbeResult,
  RankingRun,
  Team,
  TeamDetail,
  TeamParticipant,
  TeamComparison,
  Player,
  DemoListResponse,
  DemoUploadResponse,
  DemoParseFileResult,
  DemoParseResponse,
  DemoParseJob,
  DemoPlayerStatsResponse,
  DemoTournamentOption,
  DemoRankReclassifyResponse,
  DemoMapResult, DemoMapResultPatch, DemoMapOption,
  DemoRoundsResponse, DemoSideStatsResponse, DemoBombStatsResponse, DemoEconomyStatsResponse, DemoCombatStatsResponse, DemoUtilityStatsResponse,
  TeamMapsResponse,
  MapsV3Response,
  TeamMapDetail,
  CurrentRosterComparison,
  TeamMapComparisonResponse,
  TeamH2HComparison,
  MatchBackfillResult, MatchEnvironment, MatchFormat, MatchListResponse, MatchResolution, MatchSeries, MatchStage, TeamMatchStats, TeamVetoProfile, VetoAction, VetoComparison, CalculatedVeto, MatchupScore, WinProbability,
  AnalystFactor, AnalystFactorPayload, MLModelsStatus, MLFeatureDiagnosticsReport,
  BettingRestrictions, HEKillBacktestReport, HEKillByMapPrediction, MatchLLMAnalysisRun, MatchLLMGenerateRequest, MatchLLMHistoryItem, PredictionHistoryResponse, MatchupCalibrationReport,
} from "./types";

export class ApiError extends Error {
  constructor(public status:number,public code:string|null,message:string){super(message);this.name="ApiError"}
}


async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;

    let code:string|null=null;
    try {
      const payload:{detail?:string|{code?:string;message?:string}}=await response.json();
      if(typeof payload.detail==="string")detail=payload.detail;
      else if(payload.detail){detail=payload.detail.message||detail;code=payload.detail.code||null}
    } catch {
      // Keep the HTTP fallback for non-JSON failures.
    }

    throw new ApiError(response.status,code,detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getDemoMapResult(id: number): Promise<DemoMapResult> {
  return request<DemoMapResult>(`/api/v1/demos/${id}/map-result`);
}

export function patchDemoMapResult(id: number, payload: DemoMapResultPatch): Promise<DemoMapResult> {
  return request<DemoMapResult>(`/api/v1/demos/${id}/map-result`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
}

export function getDemoMaps(): Promise<{ items: DemoMapOption[] }> {
  return request<{ items: DemoMapOption[] }>("/api/v1/meta/maps");
}

export function getDemoRounds(id: number, filter = "all", page = 1): Promise<DemoRoundsResponse> {
  const query = new URLSearchParams({ page: String(page), page_size: "50" });
  if (filter === "regulation" || filter === "overtime") query.set("phase", filter);
  if (filter === "CT" || filter === "T") query.set("winner_side", filter);
  return request<DemoRoundsResponse>(`/api/v1/demos/${id}/rounds?${query}`);
}

export function getDemoSideStats(id: number): Promise<DemoSideStatsResponse> {
  return request<DemoSideStatsResponse>(`/api/v1/demos/${id}/side-stats`);
}

export function getDemoBombStats(id: number): Promise<DemoBombStatsResponse> {
  return request<DemoBombStatsResponse>(`/api/v1/demos/${id}/bomb-stats`);
}

export function getDemoEconomyStats(id: number): Promise<DemoEconomyStatsResponse> {
  return request<DemoEconomyStatsResponse>(`/api/v1/demos/${id}/economy-stats`);
}

export function getDemoCombatStats(id: number): Promise<DemoCombatStatsResponse> {
  return request<DemoCombatStatsResponse>(`/api/v1/demos/${id}/combat-stats`);
}
export function getDemoUtilityStats(id: number): Promise<DemoUtilityStatsResponse> {
  return request<DemoUtilityStatsResponse>(`/api/v1/demos/${id}/utility-stats`);
}

export function recalculateDemoSideStats(id: number): Promise<DemoSideStatsResponse> {
  return request<DemoSideStatsResponse>(`/api/v1/demos/${id}/recalculate-side-stats`, { method: "POST" });
}

export function getPlayer(id: number): Promise<Player> {
  return request<Player>(`/api/v1/players/${id}`);
}

export function refreshPlayer(id: number): Promise<Player> {
  return request<Player>(`/api/v1/players/${id}/refresh`, { method: "POST" });
}


export function getTeams(): Promise<Team[]> {
  return request<Team[]>("/api/v1/teams");
}

export function getTeam(id: number): Promise<TeamDetail> {
  return request<TeamDetail>(`/api/v1/teams/${id}`);
}
export function getTeamStrengthV3(id: number): Promise<TeamDetail["team_strength_v3"]> {
  return request<TeamDetail["team_strength_v3"]>(`/api/v1/teams/${id}/strength-v3`);
}
export function getTeamFormV3(id: number): Promise<TeamDetail["form_v3"]> {
  return request<TeamDetail["form_v3"]>(`/api/v1/teams/${id}/form-v3`);
}
export function createAnalystFactor(payload:AnalystFactorPayload):Promise<AnalystFactor>{return request("/api/v1/analyst-factors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function updateAnalystFactor(id:number,payload:Partial<AnalystFactorPayload>):Promise<AnalystFactor>{return request(`/api/v1/analyst-factors/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export async function deleteAnalystFactor(id:number):Promise<void>{await request(`/api/v1/analyst-factors/${id}`,{method:"DELETE"})}

export function getTeamMaps(id: number, level: "organization" | "current_roster" = "organization"): Promise<TeamMapsResponse> {
  return request<TeamMapsResponse>(`/api/v1/analysis/teams/${id}/maps?aggregation_level=${level}`);
}
export async function getTeamMapsV3(id:number, query=""):Promise<MapsV3Response>{
  const value=await request<Omit<MapsV3Response,"maps"> & {maps:Array<{map:string;map_strength_v3:MapsV3Response["maps"][number]}>}>(`/api/v1/analysis/teams/${id}/maps-v3${query}`);
  return {...value,maps:value.maps.map(item=>item.map_strength_v3)};
}
export function getTeamMapV3(id:number,map:string,query=""):Promise<{map_strength_v3:MapsV3Response["maps"][number]}>{return request(`/api/v1/analysis/teams/${id}/maps-v3/${encodeURIComponent(map)}${query}`)}

export function getTeamMapDetail(id: number, mapName: string, level: "organization" | "current_roster" = "organization"): Promise<TeamMapDetail> {
  return request<TeamMapDetail>(`/api/v1/analysis/teams/${id}/maps/${encodeURIComponent(mapName)}?aggregation_level=${level}`);
}

export function compareCurrentRosters(a: number, b: number): Promise<CurrentRosterComparison> {
  return request<CurrentRosterComparison>(`/api/v1/analysis/compare/teams/${a}/${b}/current-rosters`);
}

export function getTeamH2H(teamAId: number, teamBId: number, recentLimit = 10): Promise<TeamH2HComparison> {
  return request<TeamH2HComparison>(`/api/v1/analysis/compare/teams/${teamAId}/${teamBId}/h2h?recent_limit=${recentLimit}`);
}

export function getMatches(resolutionStatus?: MatchResolution,vetoFilter?:"expected_missing"|"has_veto"): Promise<MatchListResponse> {
  const query=new URLSearchParams();if(resolutionStatus)query.set("resolution_status",resolutionStatus);if(vetoFilter)query.set("veto_filter",vetoFilter);
  return request<MatchListResponse>(`/api/v1/matches${query.size?`?${query}`:""}`);
}
export function backfillMatches(): Promise<MatchBackfillResult> { return request<MatchBackfillResult>("/api/v1/matches/backfill", { method: "POST" }); }
export function getMatch(id: number): Promise<MatchSeries> { return request<MatchSeries>(`/api/v1/matches/${id}`); }
export function capturePredictionHistory(matchId:number,retrospective=false):Promise<{id:number;match_id:number;created_at:string}>{return request("/api/v1/prediction-history/snapshots",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({match_id:matchId,retrospective})})}
export function captureTournamentPredictionHistory(tournamentId:number):Promise<{tournament_id:number;eligible:number;created:number;existing:number;created_match_ids:number[];errors:Array<{match_id:number;message:string}>}>{return request(`/api/v1/prediction-history/tournaments/${tournamentId}/snapshots`,{method:"POST"})}
export function getPredictionHistory(filters:{tournamentId?:number;date?:string;status?:"completed"|"future";consensus?:boolean;conflictOnly?:boolean;strongConflicts?:boolean;source?:"pre_match"|"retrospective";mlModelVersion?:string;matchupModelVersion?:string;comparisonType?:string;matchupErrorDriver?:string;errorResult?:string;mlConfidenceError?:number}={}):Promise<PredictionHistoryResponse>{const q=new URLSearchParams();if(filters.tournamentId)q.set("tournament_id",String(filters.tournamentId));if(filters.date)q.set("match_date",filters.date);if(filters.status)q.set("status",filters.status);if(filters.consensus)q.set("consensus_3_3","true");if(filters.conflictOnly)q.set("conflict_only","true");if(filters.strongConflicts)q.set("strong_conflicts","true");if(filters.source)q.set("source",filters.source);if(filters.mlModelVersion)q.set("ml_model_version",filters.mlModelVersion);if(filters.matchupModelVersion)q.set("matchup_model_version",filters.matchupModelVersion);if(filters.comparisonType)q.set("comparison_type",filters.comparisonType);if(filters.matchupErrorDriver)q.set("matchup_error_driver",filters.matchupErrorDriver);if(filters.errorResult)q.set("error_result",filters.errorResult);if(filters.mlConfidenceError)q.set("ml_confidence_error",String(filters.mlConfidenceError));return request(`/api/v1/prediction-history${q.size?`?${q}`:""}`)}
export function createMatchSeries(demoFileIds: number[], format: MatchFormat, stage: MatchStage, environment: MatchEnvironment): Promise<MatchSeries> {
  return request<MatchSeries>("/api/v1/matches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo_file_ids: demoFileIds, format, stage, environment, resolution_status: "resolved" }) });
}
export function patchMatchSeries(id: number, payload: Partial<{tournament_id:number;format: MatchFormat; stage: MatchStage; environment: MatchEnvironment; resolution_status: MatchResolution; is_playoff: boolean; is_elimination: boolean;round_number:number|null;round_label:string|null;group_name:string|null;bracket_section:"main"|"upper"|"lower"|"group"|"swiss"|null;bracket_position:number|null;next_match_id:number|null;next_match_slot:"team_a"|"team_b"|null;loser_next_match_id:number|null;loser_next_match_slot:"team_a"|"team_b"|null}>): Promise<MatchSeries> {
  return request<MatchSeries>(`/api/v1/matches/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export function reorderMatchSeries(id: number, demoFileIds: number[]): Promise<MatchSeries> {
  return request<MatchSeries>(`/api/v1/matches/${id}/reorder`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo_file_ids: demoFileIds }) });
}
export function splitMatchSeries(id: number, demoFileIds?: number[]): Promise<MatchSeries[]> {
  return request<MatchSeries[]>(`/api/v1/matches/${id}/split`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo_file_ids: demoFileIds }) });
}
export function getTeamMatchStats(id: number, level: "organization" | "current_roster"): Promise<TeamMatchStats> {
  return request<TeamMatchStats>(`/api/v1/analysis/teams/${id}/matches?aggregation_level=${level}`);
}
export function getTeamVeto(id:number,level:"organization"|"current_roster"="organization"):Promise<TeamVetoProfile>{return request(`/api/v1/analysis/teams/${id}/veto?aggregation_level=${level}`)}
export function compareTeamVeto(a:number,b:number,level:"organization"|"current_roster"="current_roster"):Promise<VetoComparison>{return request(`/api/v1/analysis/compare/teams/${a}/${b}/veto?aggregation_level=${level}`)}
export function getCalculatedVeto(a:number,b:number):Promise<CalculatedVeto>{return request(`/api/v1/analysis/calculated-veto?team_a_id=${a}&team_b_id=${b}&format=bo3`)}
export function getMatchupScore(a:number,b:number,format:"bo1"|"bo3"|"bo5"="bo3",analysisMode:"pre_veto"|"post_veto"="pre_veto",seriesId?:number):Promise<MatchupScore>{const q=new URLSearchParams({team_a_id:String(a),team_b_id:String(b),format,analysis_mode:analysisMode});if(seriesId)q.set("series_id",String(seriesId));return request(`/api/v1/analysis/matchup?${q}`)}
export function getMatchupCalibration(limit=120):Promise<MatchupCalibrationReport>{return request(`/api/v1/analysis/matchup-calibration?limit=${limit}`)}
export function getOpponentContext(teamId:number,asOf?:string,tournamentId?:number):Promise<any>{const q=new URLSearchParams({team_id:String(teamId)});if(asOf)q.set("as_of",asOf);if(tournamentId)q.set("tournament_id",String(tournamentId));return request(`/api/v1/analysis/opponent-context?${q}`)}
export function getWinProbability(a:number,b:number,format:"bo1"|"bo3"|"bo5"="bo3",analysisMode:"pre_veto"|"post_veto"="pre_veto",seriesId?:number):Promise<WinProbability>{const q=new URLSearchParams({team_a_id:String(a),team_b_id:String(b),format,analysis_mode:analysisMode});if(seriesId)q.set("series_id",String(seriesId));return request(`/api/v1/analysis/win-probability?${q}`)}
export function getHEKillByMap(a:number,b:number,matchId?:number):Promise<HEKillByMapPrediction[]>{const q=new URLSearchParams({team_a_id:String(a),team_b_id:String(b),as_of:new Date().toISOString()});if(matchId)q.set("match_id",String(matchId));return request(`/api/v1/analysis/he-kill-by-map?${q}`)}
export function getHEKillBacktest():Promise<HEKillBacktestReport>{return request("/api/v1/analysis/he-kill-by-map/backtest")}
export function getBettingRestrictions(a:number,b:number,matchId?:number):Promise<BettingRestrictions>{return request(`/api/v1/analysis/betting-restrictions?team_a_id=${a}&team_b_id=${b}${matchId?`&match_id=${matchId}`:""}`)}
export async function getLatestMatchLLMAnalysis(teamAId:number,teamBId:number,matchId?:number):Promise<MatchLLMAnalysisRun|null>{const q=new URLSearchParams({team_a_id:String(teamAId),team_b_id:String(teamBId),analysis_mode:"pre_match"});if(matchId)q.set("match_id",String(matchId));try{return await request(`/api/v1/analysis/llm-match-analysis/latest?${q}`)}catch(error){if(error instanceof ApiError&&error.status===404)return null;throw error}}
export function generateMatchLLMAnalysis(payload:MatchLLMGenerateRequest):Promise<MatchLLMAnalysisRun>{return request("/api/v1/analysis/llm-match-analysis/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function getMatchLLMAnalysisRun(id:number):Promise<MatchLLMAnalysisRun>{return request(`/api/v1/analysis/llm-match-analysis/${id}`)}
export function getMatchLLMAnalysisHistory(teamAId:number,teamBId:number,matchId?:number):Promise<MatchLLMHistoryItem[]>{const q=new URLSearchParams({team_a_id:String(teamAId),team_b_id:String(teamBId),limit:"50",offset:"0"});if(matchId)q.set("match_id",String(matchId));return request(`/api/v1/analysis/llm-match-analysis/history?${q}`)}
export function regenerateMatchLLMAnalysis(id:number):Promise<MatchLLMAnalysisRun>{return request(`/api/v1/analysis/llm-match-analysis/${id}/regenerate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reuse_context:true})})}
export function getMLModels():Promise<MLModelsStatus>{return request("/api/v1/ml/models")}
export function activateMLModel(id:number,force:boolean):Promise<unknown>{return request(`/api/v1/ml/models/${id}/activate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({force})})}
export function trainMLModel():Promise<unknown>{return request("/api/v1/analysis/win-probability/train",{method:"POST"})}
export function getLatestMLFeatureDiagnostics():Promise<MLFeatureDiagnosticsReport>{return request("/api/v1/ml/models/feature-diagnostics/latest")}
export function runMLFeatureDiagnostics():Promise<MLFeatureDiagnosticsReport>{return request("/api/v1/ml/models/feature-diagnostics/run",{method:"POST"})}
export function getModelSandbox():Promise<any>{return request("/api/v1/admin/model-sandbox")}
export function previewSandboxMatchup(match_id:number,config:unknown):Promise<any>{return request("/api/v1/admin/model-sandbox/matchup/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({match_id,config})})}
export function backtestSandboxMatchup(config:unknown):Promise<any>{return request("/api/v1/admin/model-sandbox/matchup/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({config})})}
export function trainSandboxML(enabled_features:string[]):Promise<any>{return request("/api/v1/admin/model-sandbox/ml/train",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled_features})})}
export function updateMatchVeto(id:number,actions:VetoAction[],status:MatchSeries["veto_data_status"]):Promise<MatchSeries>{return request(`/api/v1/matches/${id}/veto`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({actions,status})})}
export function updateMatchVetoText(id:number,text:string,status:MatchSeries["veto_data_status"]):Promise<MatchSeries>{return request(`/api/v1/matches/${id}/veto`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,status})})}
export function getTournaments():Promise<import("./types").TournamentListResponse>{return request("/api/v1/tournaments")}
export function createTournament(payload:import("./types").TournamentCreate):Promise<{id:number}>{return request("/api/v1/tournaments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function createTournamentMatch(id:number,payload:import("./types").TournamentCreate["matches"][number]):Promise<MatchSeries>{return request(`/api/v1/tournaments/${id}/matches`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function importTournamentTeam(slug_or_url:string):Promise<{id:number;name:string}>{return request("/api/v1/tournaments/import-team",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({slug_or_url})})}
export function getTournamentView(id:number):Promise<import("./types").TournamentView>{return request(`/api/v1/tournaments/${id}/view`)}
export function getEffectiveTournamentRoster(tournamentId:number,teamId:number):Promise<import("./types").EffectiveTournamentRoster>{return request(`/api/v1/tournaments/${tournamentId}/teams/${teamId}/effective-roster`)}
export function createTournamentRosterOverride(tournamentId:number,payload:{team_id:number;player_out_id:number;player_in_id:number;notes?:string|null}):Promise<unknown>{return request(`/api/v1/tournaments/${tournamentId}/roster-overrides`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function disableTournamentRosterOverride(tournamentId:number,id:number):Promise<void>{return request(`/api/v1/tournaments/${tournamentId}/roster-overrides/${id}`,{method:"DELETE"})}
export function checkTournamentRoster(tournamentId:number,teamId:number):Promise<{status:string}>{return request(`/api/v1/tournaments/${tournamentId}/teams/${teamId}/roster-overrides/check`,{method:"POST"})}
export function getTournamentPredictions(id:number):Promise<import("./types").TournamentPredictions|null>{return request(`/api/v1/tournaments/${id}/predictions`)}
export function generateTournamentPredictions(id:number):Promise<import("./types").TournamentPredictions>{return request(`/api/v1/tournaments/${id}/predictions/generate`,{method:"POST"})}
export function patchTournament(id:number,payload:Partial<{structure_type:import("./types").TournamentStructure}>):Promise<import("./types").TournamentListItem>{return request(`/api/v1/tournaments/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}

export function compareTeamMaps(
  a: number, b: number,
  level: "organization" | "current_roster" = "current_roster",
): Promise<TeamMapComparisonResponse> {
  return request<TeamMapComparisonResponse>(
    `/api/v1/analysis/compare/teams/${a}/${b}/maps?aggregation_level=${level}`,
  );
}

export function compareTeams(
  teamAId: number,
  teamBId: number,
): Promise<TeamComparison> {
  const query = new URLSearchParams({
    team_a_id: String(teamAId),
    team_b_id: String(teamBId),
  });
  return request<TeamComparison>(`/api/v1/teams/compare?${query}`);
}

export function updatePlayerRole(
  teamId: number,
  playerId: number,
  role: TeamParticipant["role"],
): Promise<TeamDetail> {
  return request<TeamDetail>(
    `/api/v1/teams/${teamId}/players/${playerId}/role`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    },
  );
}


export async function getLatestRun():
Promise<RankingRun | null> {
  const response = await fetch(
    "/api/v1/admin/bo3/top-teams/runs/latest",
  );
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json() as Promise<RankingRun>;
}


export function probeTopTeams():
Promise<ProbeResult> {
  return request<ProbeResult>(
    "/api/v1/admin/bo3/top-teams/probe",
  );
}


export function refreshTopTeams():
Promise<RankingRun> {
  return request<RankingRun>(
    "/api/v1/admin/bo3/top-teams/refresh",
    {
      method: "POST",
    },
  );
}

export function uploadDemoFiles(
  tournamentName: string,
  eventType: "online" | "lan",
  matchDate: string,
  files: File[],
  parseAfterUpload = false,
  deleteAfterSuccessfulParse = false,
): Promise<DemoUploadResponse> {
  const body = new FormData();
  body.append("tournament_name", tournamentName);
  body.append("event_type", eventType);
  body.append("match_date", matchDate);
  body.append("parse_after_upload", String(parseAfterUpload));
  body.append("delete_after_successful_parse", String(deleteAfterSuccessfulParse));
  files.forEach((file) => body.append("files", file));
  return request<DemoUploadResponse>("/api/v1/demos/upload", {
    method: "POST",
    body,
  });
}

export function getDemoFiles(
  tournamentName: string,
  year: number,
): Promise<DemoListResponse> {
  const query = new URLSearchParams({
    tournament_name: tournamentName,
    year: String(year),
  });
  return request<DemoListResponse>(`/api/v1/demos?${query}`);
}

export function getDemoTournaments(): Promise<DemoTournamentOption[]> {
  return request<DemoTournamentOption[]>("/api/v1/demos/tournaments");
}

export function parseDemoFiles(
  tournamentName: string, year: number, replaceExisting = false,
): Promise<DemoParseResponse> {
  return request<DemoParseResponse>("/api/v1/demos/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tournament_name: tournamentName,
      year,
      replace_existing: replaceExisting,
    }),
  });
}

export function parseAllDemoFiles(): Promise<DemoParseResponse> {
  return request<DemoParseResponse>("/api/v1/demos/parse-all", {
    method: "POST",
  });
}

export function startParseAllDemoJob(): Promise<DemoParseJob> {
  return request<DemoParseJob>("/api/v1/demos/parse-all/jobs", { method: "POST" });
}

export function startFilteredDemoParseJob(
  tournamentName: string, year: number, replaceExisting = false,
): Promise<DemoParseJob> {
  return request<DemoParseJob>("/api/v1/demos/parse/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tournament_name: tournamentName, year,
      replace_existing: replaceExisting,
    }),
  });
}

export function getParseAllDemoJob(jobId: string): Promise<DemoParseJob> {
  return request<DemoParseJob>(`/api/v1/demos/parse-all/jobs/${jobId}`);
}

export function parseDemoFile(
  demoFileId: number, replaceExisting = false,
): Promise<DemoParseFileResult> {
  return request<DemoParseFileResult>(
    `/api/v1/demos/${demoFileId}/parse?replace_existing=${replaceExisting}`,
    { method: "POST" },
  );
}

export function getDemoPlayerStats(
  demoFileId: number,
): Promise<DemoPlayerStatsResponse> {
  return request<DemoPlayerStatsResponse>(
    `/api/v1/demos/${demoFileId}/player-stats`,
  );
}

export function reclassifyDemoOpponentRanks(
  demoFileId: number,
): Promise<DemoRankReclassifyResponse> {
  return request<DemoRankReclassifyResponse>(
    `/api/v1/demos/${demoFileId}/reclassify-opponent-ranks`,
    { method: "POST" },
  );
}

export function reclassifyOpponentRanks(
  tournamentName: string,
  year: number,
  onlyUnknownOrFallback = true,
): Promise<DemoRankReclassifyResponse> {
  return request<DemoRankReclassifyResponse>(
    "/api/v1/demos/reclassify-opponent-ranks",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tournament_name: tournamentName,
        year,
        only_unknown_or_fallback: onlyUnknownOrFallback,
      }),
    },
  );
}
