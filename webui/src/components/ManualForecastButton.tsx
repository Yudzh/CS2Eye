import {useEffect, useRef, useState} from "react";
import {createManualForecast} from "../api";

export function ManualForecastButton({matchId, disabled = false, onCreated}: {
  matchId: number; disabled?: boolean; onCreated?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const pending = useRef(false);
  const revision = useRef(0);
  useEffect(() => {
    revision.current += 1;
    pending.current = false;
    setBusy(false); setError(null); setMessage(null);
    return () => {revision.current += 1;};
  }, [matchId]);

  async function generate() {
    if (pending.current) return;
    const current = revision.current;
    pending.current = true;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await createManualForecast(matchId);
      if (revision.current !== current) return;
      if (result.prediction.status !== "available") throw new Error("Модель пока не может рассчитать прогноз.");
      setMessage(result.prediction.source === "retrospective"
        ? "Ретроспективный расчёт сохранён. Он создан после начала матча."
        : "Предматчевый прогноз сохранён.");
      onCreated?.();
    } catch (value) {
      if (revision.current === current) setError(value instanceof Error ? value.message : "Не удалось создать прогноз.");
    } finally {
      if (revision.current === current) {pending.current = false; setBusy(false);}
    }
  }
  return <div className="manual-forecast">
    <button className="button" disabled={disabled || busy} onClick={() => void generate()}>
      {busy ? "Рассчитываю прогноз…" : "Создать прогноз"}
    </button>
    {busy && <p role="status">Расчёт выполняется на сервере и может занять несколько минут.</p>}
    {message && <p role="status">{message}</p>}
    {error && <p className="map-warning" role="alert">{error}</p>}
  </div>;
}
