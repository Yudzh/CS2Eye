import { FormEvent, useEffect, useState } from "react";
import { backfillMatches, createMatchSeries, getMatches, patchMatchSeries, reorderMatchSeries, splitMatchSeries } from "../api";
import type { MatchEnvironment, MatchFormat, MatchResolution, MatchSeries, MatchStage } from "../types";

const stageLabels: Record<MatchStage, string> = { group: "Группа", swiss: "Swiss", round_of_32: "1/32", round_of_16: "1/16", quarterfinal: "Четвертьфинал", semifinal: "Полуфинал", final: "Финал", unknown: "Этап неизвестен" };
function errorText(value: unknown): string { return value instanceof Error ? value.message : "Не удалось выполнить операцию."; }

export function MatchCard({ match, admin = false, changed }: { match: MatchSeries; admin?: boolean; changed?: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  async function act(operation: () => Promise<unknown>) { setBusy(true); setError(null); try { await operation(); changed?.(); } catch (value) { setError(errorText(value)); } finally { setBusy(false); } }
  return <article className="match-series-card">
    <div className="match-series-head"><div><small>{match.tournament?.name ?? "Турнир не определён"}</small><h3><a href={`/matches/${match.id}`}>{match.team_a.name ?? "Team A"} {match.score.team_a} : {match.score.team_b} {match.team_b.name ?? "Team B"}</a></h3><span>{stageLabels[match.stage]} · {match.format.toUpperCase()} · {match.environment.toUpperCase()} · {new Date(`${match.match_date}T00:00:00`).toLocaleDateString("ru-RU")}</span></div><span className={`match-resolution match-resolution--${match.resolution_status}`}>{match.resolution_status}</span></div>
    <ol className="match-map-list">{match.maps.map((map) => <li key={map.demo_file_id}><a href={`/demos?demo_id=${map.demo_file_id}`}>{map.map_name ?? "Карта не определена"}</a><strong>{map.team_a_score ?? "—"}:{map.team_b_score ?? "—"}</strong><small>demo #{map.demo_file_id}</small></li>)}</ol>
    {admin && <div className="match-admin-actions">
      <label>Формат<select disabled={busy} value={match.format} onChange={(event) => void act(() => patchMatchSeries(match.id, { format: event.target.value as MatchFormat }))}><option value="bo1">BO1</option><option value="bo3">BO3</option><option value="bo5">BO5</option><option value="unknown">?</option></select></label>
      <label>Этап<select disabled={busy} value={match.stage} onChange={(event) => void act(() => patchMatchSeries(match.id, { stage: event.target.value as MatchStage }))}>{Object.entries(stageLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>Среда<select disabled={busy} value={match.environment} onChange={(event) => void act(() => patchMatchSeries(match.id, { environment: event.target.value as MatchEnvironment }))}><option value="lan">LAN</option><option value="online">Online</option><option value="unknown">?</option></select></label>
      {match.resolution_status !== "resolved" && <button className="button button--primary" disabled={busy} onClick={() => void act(() => patchMatchSeries(match.id, { resolution_status: "resolved" }))}>Подтвердить</button>}
      <button className="button" disabled={busy} onClick={() => void act(() => splitMatchSeries(match.id))}>Разделить карты</button>
      <button className="button" disabled={busy} onClick={() => void act(() => reorderMatchSeries(match.id, [...match.maps].reverse().map((map) => map.demo_file_id)))}>Обратить порядок</button>
    </div>}
    {error && <p className="map-warning">{error}</p>}
  </article>;
}

export function MatchesPage({ matchId }: { matchId?: number }) {
  const [matches, setMatches] = useState<MatchSeries[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const [demoIds, setDemoIds] = useState(""); const [format, setFormat] = useState<MatchFormat>("bo3"); const [stage, setStage] = useState<MatchStage>("unknown"); const [environment, setEnvironment] = useState<MatchEnvironment>("unknown");
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);
  const [resolutionFilter, setResolutionFilter] = useState<MatchResolution | undefined>(undefined);
  async function load() { setLoading(true); setError(null); try { const result = await getMatches(matchId ? undefined : resolutionFilter); setMatches(matchId ? result.items.filter((item) => item.id === matchId) : result.items); } catch (value) { setError(errorText(value)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [matchId, resolutionFilter]);
  async function create(event: FormEvent) { event.preventDefault(); const ids = demoIds.split(/[, ]+/).map(Number).filter(Number.isInteger); try { await createMatchSeries(ids, format, stage, environment); setDemoIds(""); await load(); } catch (value) { setError(errorText(value)); } }
  return <main className="page matches-page"><nav className="page-links"><a className="back-link" href={matchId ? "/matches" : "/demos"}>← Назад</a><strong>CS2Eye · серии</strong></nav><header className="compare-heading"><p className="eyebrow">Итерация 11</p><h1>{matchId ? "Просмотр матча" : "Матчи и серии"}</h1><p className="lead">BO1/BO3/BO5 состоят из сохранённых карт. Сомнительные объединения требуют ручного подтверждения.</p></header>
    {!matchId && <><div className="match-list-toolbar"><button className="button" onClick={() => void backfillMatches().then((result) => { setBackfillMessage(`Обработано групп: ${result.processed_groups}; resolved: ${result.resolved_matches}; требуют проверки: ${result.needs_review_matches}; ошибок: ${result.failed_groups}.`); return load(); }).catch((value) => setError(errorText(value)))}>Пересобрать серии без парсинга</button><button className={`button ${resolutionFilter === "unresolved" ? "button--primary" : ""}`} aria-pressed={resolutionFilter === "unresolved"} onClick={() => setResolutionFilter((current) => current === "unresolved" ? undefined : "unresolved")}>{resolutionFilter === "unresolved" ? "Показать все серии" : "Только unresolved"}</button></div>{backfillMessage && <p>{backfillMessage}</p>}<form className="match-create-form" onSubmit={create}><label>Demo ID через запятую<input value={demoIds} onChange={(event) => setDemoIds(event.target.value)} placeholder="500, 501, 502" /></label><label>Формат<select value={format} onChange={(event) => setFormat(event.target.value as MatchFormat)}><option value="bo1">BO1</option><option value="bo3">BO3</option><option value="bo5">BO5</option><option value="unknown">Неизвестно</option></select></label><label>Этап<select value={stage} onChange={(event) => setStage(event.target.value as MatchStage)}>{Object.entries(stageLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Среда<select value={environment} onChange={(event) => setEnvironment(event.target.value as MatchEnvironment)}><option value="lan">LAN</option><option value="online">Online</option><option value="unknown">Неизвестно</option></select></label><button className="button button--primary">Объединить вручную</button></form></>}
    {error && <div className="empty-state empty-state--error">{error}</div>}{loading ? <div className="empty-state">Загружаю серии…</div> : matches.length === 0 ? <div className="empty-state">Серии не найдены.</div> : <div className="match-series-grid">{matches.map((match) => <MatchCard key={match.id} match={match} admin={!matchId} changed={() => void load()} />)}</div>}
  </main>;
}
