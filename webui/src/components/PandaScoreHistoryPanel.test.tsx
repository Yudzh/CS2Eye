import "@testing-library/jest-dom/vitest";
import {render, screen, fireEvent, waitFor} from "@testing-library/react";
import {beforeEach, expect, it, vi} from "vitest";
import {PandaScoreHistoryPanel} from "./PandaScoreHistoryPanel";
import {getPandaScoreHistory} from "../api";
vi.mock("../api", () => ({getPandaScoreHistory: vi.fn()}));
beforeEach(() => vi.clearAllMocks());
it("shows series and refreshes the selected pair", async () => {
  vi.mocked(getPandaScoreHistory).mockResolvedValue({source:"pandascore", provider_team_id:10,
    synced_at:"2026-10-26T10:00:00Z", from:"2025-10-26", to:"2026-10-26", warning:null,
    series_played:1, wins:1, losses:0, matches:[{id:1, begin_at:"2026-10-25T10:00:00Z",
      tournament:"Test Cup", winner_id:10, teams:[{id:10,name:"G2",score:2},{id:20,name:"NAVI",score:1}]}]});
  render(<PandaScoreHistoryPanel teamId={1} opponentId={2}/>);
  expect(await screen.findByText("G2 — NAVI")).toBeInTheDocument();
  expect(screen.getByText("2:1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name:"Обновить из PandaScore"}));
  await waitFor(() => expect(getPandaScoreHistory).toHaveBeenLastCalledWith(1,2,true));
});
it("explains missing identity", async () => {
  vi.mocked(getPandaScoreHistory).mockRejectedValue(new Error("Сначала привяжите команду к PandaScore."));
  render(<PandaScoreHistoryPanel teamId={1}/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Сначала привяжите");
});
