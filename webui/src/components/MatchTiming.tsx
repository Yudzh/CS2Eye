import {useEffect, useState} from "react";
import type {ResultSync} from "../types";

function duration(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const days = Math.floor(seconds / 86400);
  const clock = [Math.floor(seconds / 3600) % 24, Math.floor(seconds / 60) % 60, seconds % 60].map(x => String(x).padStart(2, "0")).join(":");
  return `${days ? `${days} д ` : ""}${clock}`;
}
export function MatchTiming({startsAt, status, result}: {startsAt?: string | null; status: string; result?: ResultSync | null}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (status === "completed" || !startsAt || !Number.isFinite(Date.parse(startsAt))) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status, startsAt]);
  const start = startsAt ? Date.parse(startsAt) : NaN;
  const next = result?.next_check_at ? Date.parse(result.next_check_at) : NaN;
  const completed = status === "completed";
  return <div className="match-timing">
    <div><small>{completed ? "Матч завершён" : start > now ? "До начала матча" : "Начало по расписанию"}</small>
      <strong role="timer" aria-live="off">{completed ? "Результат сохранён" : Number.isNaN(start) ? "Точное время не задано" : start > now ? duration(start - now) : `${duration(now - start)} назад`}</strong>
      {startsAt && <time dateTime={startsAt}>{new Date(startsAt).toLocaleString("ru-RU")}</time>}
      {!completed && start <= now && <small>Время начала прошло; завершение ещё не подтверждено.</small>}
    </div>
    {!completed && !(start > now) && <div><small>Проверка результата</small><strong>{next > now ? `Не раньше чем через ${duration(next - now)}` : "Ожидает фоновой проверки"}</strong><small>Каждые {Math.round((result?.check_interval_seconds ?? 900) / 60)} мин · с учётом очереди и лимитов API</small></div>}
  </div>;
}
