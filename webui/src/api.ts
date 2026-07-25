import type {
  ProbeResult,
  RankingRun,
  Team,
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
