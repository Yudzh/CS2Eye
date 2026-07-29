import { useEffect, useState } from "react";

import { compareTeams, getTeams } from "../api";
import { RoleComparisonTable } from "../components/RoleComparisonTable";
import { TeamComparisonSide } from "../components/TeamComparisonSide";
import type { Team, TeamComparison } from "../types";

export function TeamComparePage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamA, setTeamA] = useState(0);
  const [teamB, setTeamB] = useState(0);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [comparison, setComparison] = useState<TeamComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadComparison(a: number, b: number) {
    setLoadingComparison(true);
    setError(null);
    try { setComparison(await compareTeams(a, b)); }
    catch (value: unknown) { setComparison(null); setError(value instanceof Error ? value.message : "Не удалось сравнить команды."); }
    finally { setLoadingComparison(false); }
  }

  useEffect(() => {
    getTeams().then((payload) => {
      const sorted = payload
        .filter((team) => team.is_analytics_active)
        .sort((a, b) => (a.current_rank ?? 999) - (b.current_rank ?? 999));
      setTeams(sorted);
      const query = new URLSearchParams(window.location.search);
      const queryA = Number(query.get("team_a"));
      const queryB = Number(query.get("team_b"));
      const validA = sorted.some((team) => team.id === queryA);
      const validB = sorted.some((team) => team.id === queryB);
      const initialA = validA ? queryA : (sorted[0]?.id ?? 0);
      const initialB = validB && queryB !== initialA ? queryB : (sorted.find((team) => team.id !== initialA)?.id ?? 0);
      setTeamA(initialA); setTeamB(initialB);
      if (validA && validB && queryA !== queryB) void loadComparison(queryA, queryB);
    }).catch((value: unknown) => setError(value instanceof Error ? value.message : "Не удалось загрузить команды."))
      .finally(() => setLoadingTeams(false));
  }, []);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!teamA || !teamB || teamA === teamB) return;
    window.history.replaceState(null, "", `/compare?team_a=${teamA}&team_b=${teamB}`);
    void loadComparison(teamA, teamB);
  }

  const insufficient = !loadingTeams && teams.length > 0 && teams.length < 2;
  return (
    <main className="page compare-page">
      <header className="compare-topbar"><a className="back-link" href="/">← К командам</a><strong>CS2Eye · сравнение</strong></header>
      <section className="compare-heading"><p className="eyebrow">Итерация 05</p><h1>Сравнение команд</h1><p className="lead">Рейтинг, текущие составы и прозрачный расчёт силы по данным из БД.</p></section>
      {loadingTeams ? <div className="empty-state">Загружаю активные команды…</div> : teams.length === 0 ? <div className="empty-state">Активный Top-30 ещё не загружен.</div> : insufficient ? <div className="empty-state">Для сравнения нужны минимум две активные команды.</div> : (
        <form className="compare-form" onSubmit={submit}>
          <label>Команда A<select value={teamA} onChange={(event) => setTeamA(Number(event.target.value))}>{teams.map((team) => <option disabled={team.id === teamB} value={team.id} key={team.id}>#{team.current_rank ?? "—"} · {team.name}</option>)}</select></label>
          <span>VS</span>
          <label>Команда B<select value={teamB} onChange={(event) => setTeamB(Number(event.target.value))}>{teams.map((team) => <option disabled={team.id === teamA} value={team.id} key={team.id}>#{team.current_rank ?? "—"} · {team.name}</option>)}</select></label>
          <button className="button button--primary" disabled={!teamA || !teamB || teamA === teamB || loadingComparison}>Сравнить</button>
        </form>
      )}
      {error && <div className="empty-state empty-state--error">{error}</div>}
      {loadingComparison ? <div className="empty-state">Собираю сравнение команд…</div> : comparison ? <>
        <section className="comparison-hero">
          <TeamComparisonSide side={comparison.team_a} />
          <div className="comparison-advantage"><small>Преимущество</small>{comparison.strength_advantage_team_name ? <><strong>{comparison.strength_advantage_team_name}</strong><span>+{comparison.strength_advantage_diff.toFixed(2)} пункта</span></> : <strong>Явного преимущества нет</strong>}</div>
          <TeamComparisonSide side={comparison.team_b} />
        </section>
        <RoleComparisonTable comparison={comparison} />
        <section className="comparison-summary"><p className="eyebrow">Краткий вывод</p><h2>Что показывает сравнение</h2><ul>{comparison.summary_notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul></section>
      </> : !loadingTeams && teams.length >= 2 && !error ? <div className="empty-state">Выберите две команды для сравнения.</div> : null}
    </main>
  );
}
