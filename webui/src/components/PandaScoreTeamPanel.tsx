import {useState} from "react";
import {searchPandaScoreTeams, updatePandaScoreTeam} from "../api";
import type {PandaScoreTeamProfile} from "../api";
import type {Team} from "../types";

export function PandaScoreTeamPanel({team, onUpdated}: {team: Team; onUpdated: (profile: Team) => void}) {
  const [query, setQuery] = useState(team.name);
  const [rows, setRows] = useState<PandaScoreTeamProfile[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null); setSaved(false);
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось получить сведения PandaScore."); }
    finally { setBusy(false); }
  }
  async function save(id: number) {
    await run(async () => { onUpdated(await updatePandaScoreTeam(team.id, id)); setRows(null); setSaved(true); });
  }
  return <section className="strength-panel">
    <h2>Сведения о команде · PandaScore</h2>
    <p>Название, страна и логотип из PandaScore.</p>
    {team.pandascore_id ? <>
      <p>Привязка: #{team.pandascore_id} · {team.pandascore_slug} · обновлено {team.pandascore_synced_at ? new Date(team.pandascore_synced_at).toLocaleString("ru-RU") : "—"}</p>
      <button className="button" disabled={busy} onClick={() => void save(team.pandascore_id!)}>{busy ? "Обновляю…" : "Обновить сведения из PandaScore"}</button>
    </> : <form onSubmit={e => {e.preventDefault(); void run(async () => setRows(await searchPandaScoreTeams(query.trim())));}}>
      <label>Название команды в PandaScore <input value={query} minLength={2} maxLength={100} required disabled={busy} onChange={e => {setQuery(e.target.value); setRows(null);}} /></label>
      <button className="button" disabled={busy || query.trim().length < 2}>{busy ? "Ищу…" : "Найти в PandaScore"}</button>
    </form>}
    {rows?.length === 0 && <p>Команды не найдены. Попробуйте другое название.</p>}
    {rows?.map(row => <div key={row.id} className="pandascore-binding">
      {row.image_url && <img src={row.image_url} alt="" width={48} height={48} />}
      <strong>{row.name}</strong><span>{row.location || "Страна не указана"} · {row.slug} · #{row.id}</span>
      <button className="button" disabled={busy} onClick={() => void save(row.id)}>Выбрать и сохранить сведения</button>
    </div>)}
    {saved && <p role="status">Сведения PandaScore сохранены.</p>}
    {error && <p role="alert" className="notice notice--error">{error}</p>}
  </section>;
}
