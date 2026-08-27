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
  TeamMapDetail,
  CurrentRosterComparison,
  TeamMapComparisonResponse,
  TeamH2HComparison,
  MatchBackfillResult, MatchEnvironment, MatchFormat, MatchListResponse, MatchResolution, MatchSeries, MatchStage, TeamMatchStats, TeamVetoProfile, VetoAction, VetoComparison, CalculatedVeto, MatchupScore, WinProbability,
  AnalystFactor, AnalystFactorPayload, MLModelsStatus,
} from "./types";


async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;

    try {
      const payload: {
        detail?: string;
      } = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep the HTTP fallback for non-JSON failures.
    }

    throw new Error(detail);
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
export function createAnalystFactor(payload:AnalystFactorPayload):Promise<AnalystFactor>{return request("/api/v1/analyst-factors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function updateAnalystFactor(id:number,payload:Partial<AnalystFactorPayload>):Promise<AnalystFactor>{return request(`/api/v1/analyst-factors/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export async function deleteAnalystFactor(id:number):Promise<void>{await request(`/api/v1/analyst-factors/${id}`,{method:"DELETE"})}

export function getTeamMaps(id: number, level: "organization" | "current_roster" = "organization"): Promise<TeamMapsResponse> {
  return request<TeamMapsResponse>(`/api/v1/analysis/teams/${id}/maps?aggregation_level=${level}`);
}

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
export function createMatchSeries(demoFileIds: number[], format: MatchFormat, stage: MatchStage, environment: MatchEnvironment): Promise<MatchSeries> {
  return request<MatchSeries>("/api/v1/matches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo_file_ids: demoFileIds, format, stage, environment, resolution_status: "resolved" }) });
}
export function patchMatchSeries(id: number, payload: Partial<{tournament_id:number;format: MatchFormat; stage: MatchStage; environment: MatchEnvironment; resolution_status: MatchResolution; is_playoff: boolean; is_elimination: boolean;round_number:number|null;round_label:string|null;group_name:string|null;bracket_section:"main"|"upper"|"lower"|"group"|"swiss"|null;bracket_position:number|null;next_match_id:number|null;next_match_slot:"team_a"|"team_b"|null}>): Promise<MatchSeries> {
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
export function getWinProbability(a:number,b:number,format:"bo1"|"bo3"|"bo5"="bo3",analysisMode:"pre_veto"|"post_veto"="pre_veto",seriesId?:number):Promise<WinProbability>{const q=new URLSearchParams({team_a_id:String(a),team_b_id:String(b),format,analysis_mode:analysisMode});if(seriesId)q.set("series_id",String(seriesId));return request(`/api/v1/analysis/win-probability?${q}`)}
export function getMLModels():Promise<MLModelsStatus>{return request("/api/v1/ml/models")}
export function activateMLModel(id:number,force:boolean):Promise<unknown>{return request(`/api/v1/ml/models/${id}/activate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({force})})}
export function trainMLModel():Promise<unknown>{return request("/api/v1/analysis/win-probability/train",{method:"POST"})}
export function updateMatchVeto(id:number,actions:VetoAction[],status:MatchSeries["veto_data_status"]):Promise<MatchSeries>{return request(`/api/v1/matches/${id}/veto`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({actions,status})})}
export function updateMatchVetoText(id:number,text:string,status:MatchSeries["veto_data_status"]):Promise<MatchSeries>{return request(`/api/v1/matches/${id}/veto`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,status})})}
export function getTournaments():Promise<import("./types").TournamentListResponse>{return request("/api/v1/tournaments")}
export function createTournament(payload:import("./types").TournamentCreate):Promise<{id:number}>{return request("/api/v1/tournaments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function createTournamentMatch(id:number,payload:import("./types").TournamentCreate["matches"][number]):Promise<MatchSeries>{return request(`/api/v1/tournaments/${id}/matches`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})}
export function importTournamentTeam(slug_or_url:string):Promise<{id:number;name:string}>{return request("/api/v1/tournaments/import-team",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({slug_or_url})})}
export function getTournamentView(id:number):Promise<import("./types").TournamentView>{return request(`/api/v1/tournaments/${id}/view`)}
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
