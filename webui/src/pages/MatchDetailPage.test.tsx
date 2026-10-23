import {cleanup, render, screen} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
const api = vi.hoisted(() => ({capturePredictionHistory: vi.fn(), getMatch: vi.fn(), getPredictionHistory: vi.fn(), getPredictionResults: vi.fn(), getPredictionFeed: vi.fn().mockResolvedValue({items: []})}));
vi.mock("../api", () => api);
vi.mock("./MatchesPage", () => ({MatchCard: () => <div>Карты матча</div>}));
import {MatchDetailPage} from "./MatchDetailPage";
afterEach(() => {cleanup(); vi.clearAllMocks();});
const match = {id: 7, team_a: {id: 1, name: "Alpha"}, team_b: {id: 2, name: "Bravo"}, winner_team_id: 2, score: {team_a: 1, team_b: 2}, status: "completed", format: "bo3", match_date: "2026-10-01", tournament: {id: 3, name: "Cup"}};
it("shows result and only this match's saved prediction", async () => {
  api.getMatch.mockResolvedValue(match);
  api.getPredictionHistory.mockResolvedValue({items: []});
  const result = {id: "p7", match_id: 7, team_a: match.team_a, team_b: match.team_b, source: "pre_match", model_version: "v12", predicted_winner: "Alpha", probability: .8, team_a_probability: .8, correct: false, captured_at: "2026-09-30T00:00:00Z"};
  api.getPredictionResults.mockResolvedValue({items: [result, {...result, id: "p8", match_id: 8, model_version: "other-model"}, {...result, id: "historical", source: "retrospective", model_version: "historical-model"}]});
  render(<MatchDetailPage matchId={7}/>);
  expect(await screen.findByText(/Наш прогноз: Alpha · 80.0%/)).toBeTruthy();
  expect(screen.getByText("1 : 2")).toBeTruthy();
  expect(screen.getByText("Bravo", {selector: "strong"})).toBeTruthy();
  expect(screen.getByText(/✕ Не угадали/)).toBeTruthy();
  expect(screen.queryByText(/other-model/)).toBeNull();
  expect(screen.queryByText(/historical-model/)).toBeNull();
});
it("keeps match visible when forecasts fail to load", async () => {
  api.getMatch.mockResolvedValue(match);
  api.getPredictionHistory.mockRejectedValue(new Error("offline"));
  api.getPredictionResults.mockResolvedValue({items: []});
  render(<MatchDetailPage matchId={7}/>);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Не удалось загрузить часть прогнозов. Обновите страницу, чтобы повторить.");
  expect(screen.getByText("1 : 2")).toBeTruthy();
  expect(screen.queryByText("Сохранённого прогноза для этого матча нет.")).toBeNull();
});
it("explains which team lacks historical round statistics", async () => {
  api.getMatch.mockResolvedValue({...match, prediction_history_coverage: {as_of: "2026-10-01", required_maps: 3, teams: [{team_id: 1, name: "Alpha", available_maps: 51}, {team_id: 2, name: "Bravo", available_maps: 2}]}});
  api.getPredictionHistory.mockResolvedValue({items: []});
  api.getPredictionResults.mockResolvedValue({items: []});
  render(<MatchDetailPage matchId={7}/>);
  expect(await screen.findByText("Bravo: доступно 2 карт с полной статистикой раундов, требуется минимум 3.")).toBeTruthy();
  expect(screen.queryByText(/Alpha: доступно/)).toBeNull();
  expect(screen.getByText(/Карты после даты матча не учитываются/)).toBeTruthy();
});

it("saves a forecast automatically when a scheduled match is opened", async () => {
  api.getMatch.mockResolvedValue({...match, status: "scheduled", match_date: "2099-10-01", winner_team_id: null});
  api.capturePredictionHistory.mockResolvedValue({id: 1});
  api.getPredictionHistory.mockResolvedValue({items: []});
  api.getPredictionResults.mockResolvedValue({items: []});
  render(<MatchDetailPage matchId={7}/>);
  await screen.findByText("Сохранённого прогноза для этого матча нет.");
  expect(api.capturePredictionHistory).toHaveBeenCalledWith(7);
  expect(screen.queryByText("Сохранить время начала")).toBeNull();
  expect(screen.queryByText("Получить прогноз")).toBeNull();
  expect(screen.queryByLabelText("Время начала (ваш часовой пояс)")).toBeNull();
  expect(api.getPredictionHistory).toHaveBeenCalled();
});
it("shows automatic save failures on the match page", async () => {
  api.getMatch.mockResolvedValue({...match, status: "scheduled", match_date: "2099-10-01", winner_team_id: null});
  api.capturePredictionHistory.mockRejectedValue(new Error("Не удалось сохранить прогноз"));
  api.getPredictionHistory.mockResolvedValue({items: []});
  api.getPredictionResults.mockResolvedValue({items: []});
  render(<MatchDetailPage matchId={7}/>);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Не удалось сохранить прогноз");
});

it("shows a restored forecast for an overdue scheduled match", async () => {
  api.getMatch.mockResolvedValue({...match, id: 382, status: "scheduled", winner_team_id: null});
  api.getPredictionHistory.mockResolvedValue({items: []});
  api.getPredictionResults.mockResolvedValue({items: []});
  api.getPredictionFeed.mockResolvedValue({items: [{match_id: 382, team_a: {id: 12, name: "9z"}, team_b: {id: 8, name: "Aurora"}, source: "retrospective", model_version: "v12", team_a_probability: .2969389, predicted_winner: "Aurora", probability: .7030611, captured_at: "2026-10-19T09:04:25Z"}]});
  render(<MatchDetailPage matchId={382}/>);
  expect(await screen.findByText("Наш прогноз: Aurora · 70.3%")).toBeTruthy();
  expect(screen.queryByText("Сохранённого прогноза для этого матча нет.")).toBeNull();
  expect(api.capturePredictionHistory).not.toHaveBeenCalled();
});
