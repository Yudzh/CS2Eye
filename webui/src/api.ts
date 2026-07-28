import type {
  ProbeResult,
  RankingRun,
  Team,
  TeamDetail,
  TeamParticipant,
  TeamComparison,
  Player,
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
