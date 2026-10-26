import {cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
import {PandaScoreTeamPanel} from "./PandaScoreTeamPanel";
import {searchPandaScoreTeams, updatePandaScoreTeam} from "../api";
import type {Team} from "../types";
vi.mock("../api", () => ({searchPandaScoreTeams:vi.fn(), updatePandaScoreTeam:vi.fn()}));
afterEach(() => {cleanup(); vi.clearAllMocks();});
const team = {id:2, name:"Aurora", pandascore_id:null} as Team;
it("previews ambiguous names and saves only the selected provider identity", async () => {
  vi.mocked(searchPandaScoreTeams).mockResolvedValue([
    {id:1,name:"Aurora Gaming",slug:"aurora-gaming",location:"RU",image_url:null},
    {id:2,name:"Aurora Young Blood",slug:"aurora-young-blood",location:"RU",image_url:null},
  ]);
  vi.mocked(updatePandaScoreTeam).mockResolvedValue({...team,name:"Aurora Gaming",pandascore_id:1});
  const updated = vi.fn();
  render(<PandaScoreTeamPanel team={team} onUpdated={updated}/>);
  fireEvent.click(screen.getByText("Найти в PandaScore"));
  await screen.findByText("Aurora Young Blood");
  expect(updatePandaScoreTeam).not.toHaveBeenCalled();
  fireEvent.click(screen.getAllByText("Выбрать и сохранить сведения")[0]);
  await waitFor(() => expect(updatePandaScoreTeam).toHaveBeenCalledWith(2,1));
  await screen.findByRole("status");
  expect(updated).toHaveBeenCalledWith(expect.objectContaining({pandascore_id:1}));
});
it("shows missing token errors without reporting a saved profile", async () => {
  vi.mocked(searchPandaScoreTeams).mockRejectedValue(new Error("На сервере не настроен PANDASCORE_API_TOKEN."));
  render(<PandaScoreTeamPanel team={team} onUpdated={vi.fn()}/>);
  fireEvent.click(screen.getByText("Найти в PandaScore"));
  expect((await screen.findByRole("alert")).textContent).toContain("PANDASCORE_API_TOKEN");
  expect(screen.queryByRole("status")).toBeNull();
});
