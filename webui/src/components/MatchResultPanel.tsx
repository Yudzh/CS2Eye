import {PandaScoreBinding} from "./PandaScoreBinding";
import {useState} from "react";
import {bindMatchResult, checkMatchResult, correctMatchResult, getMatchResultAudit} from "../api";
import type {ResultSync} from "../types";

const labels: Record<string, string> = {confirmed: "Подтверждён", manual: "Ручной результат", linked: "Привязан", needs_review: "Требует проверки", not_found: "Не найден среди завершённых", pending: "Ожидает завершения", error: "Ошибка API", disabled: "Источник не настроен"};
export function ResultStatus({value}: {value?: ResultSync | null}) {
  if (!value) return null;
  return <div><small>Источник: {value.source ?? "не указан"}{value.external_id ? ` · PandaScore #${value.external_id}` : ""}</small><small>{labels[value.status ?? ""] ?? "Ещё не проверялся"} · {value.checked_at ? new Date(value.checked_at).toLocaleString("ru-RU") : "—"}</small>{value.received_at && <small>Получен: {new Date(value.received_at).toLocaleString("ru-RU")}</small>}{value.error && <p role="status">{value.error}</p>}</div>;
}
export function CheckResultButton({matchId, changed}: {matchId: number; changed?: () => void}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return <><button className="button" disabled={busy} onClick={async () => {
    setBusy(true); setError(null);
    try {await checkMatchResult(matchId); changed?.();}
    catch (e) {setError(e instanceof Error ? e.message : "Не удалось проверить результат.");}
    finally {setBusy(false);}
  }}>Проверить результат</button>{error && <small role="alert">{error}</small>}</>;
}
export function MatchResultPanel({matchId, teamA, teamB, value, changed}: {matchId: number; teamA: {id: number | null; name: string | null}; teamB: {id: number | null; name: string | null}; value?: ResultSync | null; changed?: () => void}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<Awaited<ReturnType<typeof getMatchResultAudit>> | null>(null);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try {await fn(); changed?.();} catch (e) {setError(e instanceof Error ? e.message : "Не удалось сохранить результат.");} finally {setBusy(false);}
  }
  return <section className="strength-panel"><h3>Проверка результата</h3><PandaScoreBinding matchId={matchId} value={value}/><ResultStatus value={value}/>
    <button className="button" disabled={busy} onClick={() => void act(() => checkMatchResult(matchId))}>Проверить результат</button>
    {error && <p role="alert">{error}</p>}
    {value?.proposal && <details><summary>Данные PandaScore для ручной проверки</summary><pre style={{whiteSpace: "pre-wrap"}}>{JSON.stringify(value.proposal, null, 2)}</pre></details>}
    <details><summary>Ручная привязка к PandaScore</summary><p>Укажите ID матча и ID обеих команд из PandaScore. ID BO3 для этого не подходят. Участники будут проверены при получении результата; привязка сохраняется при переносе времени.</p>
      <form onSubmit={e => {e.preventDefault(); const f = new FormData(e.currentTarget); void act(() => bindMatchResult(matchId, {external_id: Number(f.get("external_id")), team_a_external_id: Number(f.get("team_a")), team_b_external_id: Number(f.get("team_b")), actor: f.get("actor"), reason: f.get("reason")}));}}>
        <label>ID матча PandaScore<input name="external_id" type="number" min="1" required defaultValue={value?.external_id ?? undefined}/></label>
        <label>ID PandaScore: {teamA.name}<input name="team_a" type="number" min="1" required/></label>
        <label>ID PandaScore: {teamB.name}<input name="team_b" type="number" min="1" required/></label>
        <label>Автор<input name="actor" required maxLength={160}/></label><label>Причина<input name="reason" required minLength={3} maxLength={2000}/></label>
        <button className="button" disabled={busy}>Сохранить привязку</button>
      </form>
    </details>
    <details><summary>Исправить результат вручную</summary><p>Исправление сохраняется в журнале и защищено от автоматической перезаписи. В production автор определяется по учётной записи администратора.</p>
      <form onSubmit={e => {e.preventDefault(); const f = new FormData(e.currentTarget); void act(() => correctMatchResult(matchId, {team_a: Number(f.get("a")), team_b: Number(f.get("b")), winner_team_id: Number(f.get("winner")), actor: f.get("actor"), reason: f.get("reason")}));}}>
        <label>Карты: {teamA.name}<input name="a" type="number" min="0" max="3" required/></label><label>Карты: {teamB.name}<input name="b" type="number" min="0" max="3" required/></label>
        <label>Победитель<select name="winner" required><option value="">Выберите</option><option value={teamA.id ?? ""}>{teamA.name}</option><option value={teamB.id ?? ""}>{teamB.name}</option></select></label>
        <label>Автор<input name="actor" required maxLength={160}/></label><label>Причина<input name="reason" required minLength={3} maxLength={2000}/></label>
        <button className="button" disabled={busy}>Сохранить исправление</button>
      </form>
    </details>
    <button className="button" disabled={busy} onClick={() => void act(async () => setAudit(await getMatchResultAudit(matchId)))}>Журнал изменений</button>
    {audit && <div>{audit.items.length === 0 ? <p>Изменений нет.</p> : audit.items.map(item => <details key={item.id}><summary>{new Date(item.at).toLocaleString("ru-RU")} · {item.actor} · {item.reason}</summary><pre style={{whiteSpace: "pre-wrap"}}>{JSON.stringify({before: item.before, after: item.after}, null, 2)}</pre></details>)}</div>}
  </section>;
}
