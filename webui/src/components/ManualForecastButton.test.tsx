import {act, cleanup, fireEvent, render, screen} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
const api = vi.hoisted(() => ({createManualForecast: vi.fn()}));
vi.mock("../api", () => api);
import {ManualForecastButton} from "./ManualForecastButton";
afterEach(() => {cleanup(); vi.resetAllMocks();});

it("blocks duplicate clicks and reports a retrospective result", async () => {
  let finish!: (value: unknown) => void;
  api.createManualForecast.mockReturnValue(new Promise(resolve => {finish = resolve;}));
  const created = vi.fn();
  render(<ManualForecastButton matchId={42} onCreated={created}/>);
  fireEvent.click(screen.getByRole("button", {name: "Создать прогноз"}));
  const button = screen.getByRole("button", {name: "Рассчитываю прогноз…"});
  expect(button).toHaveProperty("disabled", true);
  fireEvent.click(button);
  expect(api.createManualForecast).toHaveBeenCalledTimes(1);
  expect(api.createManualForecast).toHaveBeenCalledWith(42);
  await act(async () => {finish({prediction: {status: "available", source: "retrospective"}});});
  expect(screen.getByRole("status").textContent).toContain("после начала матча");
  expect(created).toHaveBeenCalledTimes(1);
});

it("shows the server reason and allows retry", async () => {
  api.createManualForecast.mockRejectedValueOnce(new Error("Не хватает истории"))
    .mockResolvedValueOnce({prediction: {status: "available", source: "pre_match"}});
  render(<ManualForecastButton matchId={42}/>);
  fireEvent.click(screen.getByRole("button", {name: "Создать прогноз"}));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Не хватает истории");
  fireEvent.click(screen.getByRole("button", {name: "Создать прогноз"}));
  expect(await screen.findByText("Предматчевый прогноз сохранён.")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("does not apply an old request after navigating to another match", async () => {
  let finish!: (value: unknown) => void;
  api.createManualForecast.mockReturnValue(new Promise(resolve => {finish = resolve;}));
  const created = vi.fn();
  const view = render(<ManualForecastButton matchId={42} onCreated={created}/>);
  fireEvent.click(screen.getByRole("button", {name: "Создать прогноз"}));
  view.rerender(<ManualForecastButton matchId={43} onCreated={created}/>);
  await act(async () => {finish({prediction: {status: "available", source: "pre_match"}});});
  expect(created).not.toHaveBeenCalled();
  expect(screen.queryByRole("status")).toBeNull();
});
