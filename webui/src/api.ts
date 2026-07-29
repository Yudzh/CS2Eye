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
  DemoPlayerStatsResponse,
  DemoTournamentOption,
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
  matchDate: string,
  files: File[],
): Promise<DemoUploadResponse> {
  const body = new FormData();
  body.append("tournament_name", tournamentName);
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
