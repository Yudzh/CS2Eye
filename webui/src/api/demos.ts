import {
  getJson,
} from "./client";

import type {
  DemoParseRunListResponse,
  DemoPlayerMapStatsResponse,
} from "../types";


export const demosApi = {
  listParseRuns(
    limit = 50,
  ): Promise<DemoParseRunListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      status_filter: "success",
    });

    return getJson<DemoParseRunListResponse>(
      `/demos/parse-runs?${params.toString()}`,
    );
  },


  getPlayers(
    parseRunId: string,
  ): Promise<DemoPlayerMapStatsResponse> {
    return getJson<DemoPlayerMapStatsResponse>(
      `/demos/parse-runs/${parseRunId}/players`,
    );
  },
};