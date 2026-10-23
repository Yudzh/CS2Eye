import {cleanup, fireEvent, render, screen, within} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
import type {PredictionFeedItem} from "../types";
const api = vi.hoisted(() => ({getPredictionFeed: vi.fn()}));
vi.mock("../api", () => api);
import {PredictionsPage} from "./PredictionsPage";
afterEach(() => {cleanup(); vi.clearAllMocks(); window.history.replaceState(null, "", "/predictions");});
const upcoming: PredictionFeedItem = {match_id:1, match_date:"2026-10-15", starts_at:null, status:"scheduled", tournament_id:1, tournament:"Thunderpick", format:"bo3", team_a:{id:1,name:"Alpha"}, team_b:{id:2,name:"Bravo"}, team_a_probability:.8, probability:.8, predicted_winner:"Alpha", actual_winner:null, correct:null, score:null, source:"pre_match", model_version:"v12", captured_at:"2026-10-14T08:00:00Z"};
const played: PredictionFeedItem = {...upcoming, match_id:2, status:"completed", match_date:"2026-10-14", score:{team_a:0,team_b:2}, actual_winner:"Bravo", correct:false};
it("shows upcoming picks first and switches to scored results", async () => {
  api.getPredictionFeed.mockResolvedValue({items:[upcoming,played]});
  render(<PredictionsPage/>);
  await screen.findByRole("link",{name:"Alpha — Bravo"});
  expect(screen.getByRole("tab", {name:/Предстоящие/}).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByText("Ожидает игры")).toBeTruthy();
  expect(screen.queryByText("✕ Не угадали")).toBeNull();
  fireEvent.click(screen.getByRole("tab",{name:/Сыгранные/}));
  expect(screen.getByText("✕ Не угадали")).toBeTruthy();
  expect(screen.getByText("0 : 2")).toBeTruthy();
  expect(window.location.search).toContain("tab=completed");
});
it("includes restored picks without mixing them into pre-match accuracy", async () => {
  api.getPredictionFeed.mockResolvedValue({items:[played,{...played,match_id:3,source:"retrospective",correct:true}]});
  render(<PredictionsPage initialTab="completed"/>);
  await screen.findByText("Восстановленный прогноз · v12");
  const stats = screen.getByRole("region", {name:"Точность прогнозов"});
  expect(within(stats).getByText("0.0%")).toBeTruthy();
  expect(within(stats).getByText("100.0%")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Результат"),{target:{value:"miss"}});
  expect(screen.getAllByRole("link",{name:"Alpha — Bravo"})).toHaveLength(1);
  expect(within(stats).getByText("0.0%")).toBeTruthy();
});
it("keeps known matches without saved picks visible", async () => {
  api.getPredictionFeed.mockResolvedValue({items:[{...upcoming,team_a_probability:null,probability:null,predicted_winner:null,source:null,captured_at:null,model_version:null}]});
  render(<PredictionsPage/>);
  await screen.findByText("Прогноз ещё не сохранён");
  expect(screen.getByText("Ожидает прогноза")).toBeTruthy();
});
it("filters by team and resets an empty search", async () => {
  api.getPredictionFeed.mockResolvedValue({items:[upcoming]});
  render(<PredictionsPage/>);
  await screen.findByRole("link",{name:"Alpha — Bravo"});
  fireEvent.change(screen.getByLabelText("Поиск"),{target:{value:"Missing"}});
  expect(screen.getByText("По этим фильтрам матчей нет")).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"Сбросить"}));
  expect(screen.getByRole("link",{name:"Alpha — Bravo"})).toBeTruthy();
});
it("retries a failed load", async () => {
  api.getPredictionFeed.mockRejectedValueOnce(new Error("Нет соединения")).mockResolvedValueOnce({items:[]});
  render(<PredictionsPage/>);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button",{name:"Повторить"}));
  await screen.findByText("Предстоящих матчей пока нет");
});
