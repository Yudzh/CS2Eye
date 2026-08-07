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
  DemoRoundsResponse, DemoSideStatsResponse,
  TeamMapsResponse,
  TeamMapDetail,
  CurrentRosterComparison,
  TeamMapComparisonResponse,
  TeamH2HComparison,
  MatchBackfillResult, MatchEnvironment, MatchFormat, MatchListResponse, MatchResolution, MatchSeries, MatchStage, TeamMatchStats,
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

export function getMatches(resolutionStatus?: MatchResolution): Promise<MatchListResponse> {
  return request<MatchListResponse>(`/api/v1/matches${resolutionStatus ? `?resolution_status=${resolutionStatus}` : ""}`);
}
export function backfillMatches(): Promise<MatchBackfillResult> { return request<MatchBackfillResult>("/api/v1/matches/backfill", { method: "POST" }); }
export function getMatch(id: number): Promise<MatchSeries> { return request<MatchSeries>(`/api/v1/matches/${id}`); }
export function createMatchSeries(demoFileIds: number[], format: MatchFormat, stage: MatchStage, environment: MatchEnvironment): Promise<MatchSeries> {
  return request<MatchSeries>("/api/v1/matches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ demo_file_ids: demoFileIds, format, stage, environment, resolution_status: "resolved" }) });
}
export function patchMatchSeries(id: number, payload: Partial<{format: MatchFormat; stage: MatchStage; environment: MatchEnvironment; resolution_status: MatchResolution; is_playoff: boolean; is_elimination: boolean}>): Promise<MatchSeries> {
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
): Promise<DemoUploadResponse> {
  const body = new FormData();
  body.append("tournament_name", tournamentName);
  body.append("event_type", eventType);
  body.append("match_date", matchDate);
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
