import {
  getJson,
  postJson,
  deleteJson,
  patchJson,
} from "./client";

import type {
  LiquipediaTeamRequest,
  LiquipediaTeamResponse,
  TeamComparisonDashboard,
  TeamDashboard,
  TeamSummaryListResponse,
  AdminTeam,
  AdminTeamListResponse,
  ManualRosterUpdateRequest,
  TeamDeleteResponse,
  TeamRoleOption,
} from "../types";


export const teamsApi = {
  list(): Promise<TeamSummaryListResponse> {
    return getJson<TeamSummaryListResponse>(
      "/teams/summaries",
    );
  },


  listAdmin(): Promise<
    AdminTeamListResponse
  > {
    return getJson<
      AdminTeamListResponse
    >(
      "/teams",
    );
  },


  getRoleOptions(): Promise<
    TeamRoleOption[]
  > {
    return getJson<
      TeamRoleOption[]
    >(
      "/teams/role-options",
    );
  },


  updateRoster(
    teamName: string,
    request: ManualRosterUpdateRequest,
  ): Promise<AdminTeam> {
    const params = new URLSearchParams({
      team_name: teamName,
    });

    return patchJson<AdminTeam>(
      `/teams/by-name/roster?${params.toString()}`,
      request,
    );
  },


  deleteTeam(
    teamName: string,
  ): Promise<TeamDeleteResponse> {
    const params = new URLSearchParams({
      team_name: teamName,
    });

    return deleteJson<
      TeamDeleteResponse
    >(
      `/teams/by-name?${params.toString()}`,
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