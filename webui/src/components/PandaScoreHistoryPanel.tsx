import {useEffect, useRef, useState} from "react";
import {getPandaScoreHistory} from "../api";
import type {PandaScoreHistory} from "../api";

export function PandaScoreHistoryPanel({teamId, opponentId}: {teamId: number; opponentId?: number}) {
  const [data, setData] = useState<PandaScoreHistory | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  async function load(refresh = false) {
    const id = ++generation.current;
    setBusy(true); setError(null);
    try {
      const result = await getPandaScoreHistory(teamId, opponentId, refresh);
      if (id === generation.current) setData(result);
    } catch (e) {
      if (id === generation.current) setError(e instanceof Error ? e.message : "Не удалось загрузить историю.");
    } finally { if (id === generation.current) setBusy(false); }
  }
  useEffect(() => {setData(null); void load(); return () => {generation.current++;};}, [teamId, opponentId]);
  return <section className="strength-panel">
    <div className="section-heading"><div><p className="eyebrow">PandaScore · история серий</p>
      <h2>{opponentId ? "Личные встречи PandaScore" : "История матчей PandaScore"}</h2></div>
      <button disabled={busy} onClick={() => void load(true)}>{busy ? "Загружаю…" : "Обновить из PandaScore"}</button></div>
    <p>Завершённые серии за последние 365 дней в покрытии PandaScore. Технические победы и ничьи исключены. Составы конкретных матчей не подтверждены.</p>
    {error && <p role="alert">{error}</p>}
    {data && <><p>{data.series_played} серий · {data.wins} побед · {data.losses} поражений · Обновлено: {new Date(data.synced_at).toLocaleString()}</p>
      {data.warning && <p role="alert">Сохранённые данные: {data.warning}</p>}
      {data.matches.length ? <div className="table-scroll"><table><thead><tr><th>Дата</th><th>Турнир</th><th>Матч</th><th>Счёт</th><th>Итог</th></tr></thead>
        <tbody>{data.matches.map(match => <tr key={match.id}><td>{new Date(match.begin_at).toLocaleDateString()}</td><td>{match.tournament}</td>
          <td>{match.teams.map(t => t.name).join(" — ")}</td><td>{match.teams.map(t => t.score).join(":")}</td>
          <td>{match.winner_id === data.provider_team_id ? "Победа" : "Поражение"}</td></tr>)}</tbody></table></div> : <p>В этом периоде встреч не найдено.</p>}</>}
  </section>;
}
