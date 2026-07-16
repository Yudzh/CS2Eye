import {
  getJson,
  postJson,
} from "./client";

import type {
  LiquipediaTeamRequest,
  LiquipediaTeamResponse,
  TeamComparisonDashboard,
  TeamDashboard,
  TeamSummaryListResponse,
} from "../types";


export const teamsApi = {
  list(): Promise<TeamSummaryListResponse> {
    return getJson<TeamSummaryListResponse>(
      "/teams/summaries",
    );
  },


  getDashboard(
    teamId: string,
  ): Promise<TeamDashboard> {
    return getJson<TeamDashboard>(
      `/teams/${teamId}/dashboard`,
    );
  },


  compare(
    teamAId: string,
    teamBId: string,
  ): Promise<TeamComparisonDashboard> {
    const params = new URLSearchParams({
      team_a_id: teamAId,
      team_b_id: teamBId,
    });

    return getJson<TeamComparisonDashboard>(
      `/teams/compare?${params.toString()}`,
    );
  },


  importFromLiquipedia(
    request: LiquipediaTeamRequest,
  ): Promise<LiquipediaTeamResponse> {
    return postJson<LiquipediaTeamResponse>(
      "/teams/liquipedia",
      request,
    );
  },
};