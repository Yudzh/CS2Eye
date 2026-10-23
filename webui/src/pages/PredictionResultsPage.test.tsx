import {cleanup, fireEvent, render, screen, within} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";
import type {PredictionResult} from "../types";
const api = vi.hoisted(() => ({getPredictionResults: vi.fn()}));
vi.mock("../api", () => api);
import {PredictionResultsPage} from "./PredictionResultsPage";
afterEach(() => {cleanup(); vi.clearAllMocks();});
const row: PredictionResult = {id:"pre_match:1", match_id:1, tournament_id:1, tournament:"Cup", match_date:"2026-10-03", format:"bo3", score:{team_a:2,team_b:0}, team_a:{id:1,name:"Alpha"}, team_b:{id:2,name:"Bravo"}, model_version:"v12", source:"pre_match", captured_at:"2026-10-02T00:00:00Z", team_a_probability:.8, predicted_winner:"Alpha", probability:.8, actual_winner:"Alpha", correct:true};

describe("Prediction results", () => {
  it("separates retrospective results and keeps accuracy when filtering misses", async () => {
    api.getPredictionResults.mockResolvedValue({active_model_version:"v12", items:[row, {...row,id:"pre_match:2",match_id:2,predicted_winner:"Bravo",correct:false}, {...row,id:"retrospective:3",source:"retrospective",model_version:"v13"}]});
    render(<PredictionResultsPage/>);
    await screen.findAllByRole("link", {name:"Alpha 2 : 0 Bravo"});
    const stats = screen.getByRole("region", {name:"Статистика прогнозов"});
    expect(within(stats).getByText("50.0%")).toBeTruthy();
    expect(screen.queryByText("v13 · Исторический расчёт")).toBeNull();
    fireEvent.change(screen.getByLabelText("Результат"), {target:{value:"miss"}});
    expect(screen.getAllByRole("link", {name:"Alpha 2 : 0 Bravo"})).toHaveLength(1);
    expect(within(stats).getByText("50.0%")).toBeTruthy();
    expect(screen.queryByRole("button", {name:"Исторический расчёт"})).toBeNull();
  });
  it("shows reconstructed forecasts when no saved pre-match forecasts exist", async () => {
    api.getPredictionResults.mockResolvedValue({active_model_version:"v12",items:[{...row,source:"retrospective"}]});
    render(<PredictionResultsPage/>);
    await screen.findByRole("link", {name:"Alpha 2 : 0 Bravo"});
    expect(screen.getByText("v12 · Восстановленный прогноз")).toBeTruthy();
  });
  it("shows errors and retries", async () => {
    api.getPredictionResults.mockRejectedValueOnce(new Error("Сеть недоступна")).mockResolvedValueOnce({items:[],active_model_version:null});
    render(<PredictionResultsPage/>);
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button",{name:"Повторить"}));
    await screen.findByText(/Завершённых матчей с сохранённым ML-прогнозом пока нет/);
  });
});
