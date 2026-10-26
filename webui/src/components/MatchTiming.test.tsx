import {act, cleanup, render, screen} from "@testing-library/react";
import {afterEach, beforeEach, expect, it, vi} from "vitest";
import {MatchTiming} from "./MatchTiming";
beforeEach(() => {vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-26T12:00:00Z"));});
afterEach(() => {cleanup(); vi.useRealTimers();});
it("counts down and changes to elapsed scheduled time without claiming a live result", () => {
  render(<MatchTiming startsAt="2026-10-26T12:00:02Z" status="scheduled"/>);
  expect(screen.getByRole("timer").textContent).toBe("00:00:02");
  act(() => {vi.advanceTimersByTime(3000);});
  expect(screen.getByRole("timer").textContent).toBe("00:00:01 назад");
  expect(screen.getByText("Время начала прошло; завершение ещё не подтверждено.")).toBeTruthy();
});
it("shows deferred check and stops promising an exact time once due", () => {
  const result={source:null,external_id:null,received_at:null,checked_at:null,status:null,error:null,manual:false,link:null,proposal:null,next_check_at:"2026-10-26T12:00:02Z",check_interval_seconds:900};
  render(<MatchTiming startsAt="2026-10-24T12:00:00Z" status="scheduled" result={result}/>);
  expect(screen.getByText("Не раньше чем через 00:00:02")).toBeTruthy();
  expect(screen.getByRole("timer").textContent).toBe("2 д 00:00:00 назад");
  act(() => {vi.advanceTimersByTime(3000);});
  expect(screen.getByText("Ожидает фоновой проверки")).toBeTruthy();
});
it("handles unknown kickoff and a completed match", () => {
  const {rerender}=render(<MatchTiming status="scheduled"/>);
  expect(screen.getByRole("timer").textContent).toBe("Точное время не задано");
  rerender(<MatchTiming status="completed"/>);
  expect(screen.getByRole("timer").textContent).toBe("Результат сохранён");
  expect(screen.queryByText("Ожидает фоновой проверки")).toBeNull();
});
