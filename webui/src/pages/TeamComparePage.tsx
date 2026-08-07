import { useEffect, useState } from "react";

import { compareTeamMaps, compareTeams, getTeamH2H, getTeams } from "../api";
import { RoleComparisonTable } from "../components/RoleComparisonTable";
import { TeamComparisonSide } from "../components/TeamComparisonSide";
import type { MapConfidenceLevel, Team, TeamComparison, TeamH2HComparison, TeamH2HRosterContext, TeamH2HSlice, TeamMapComparisonItem, TeamMapComparisonResponse } from "../types";

const confidenceLabels: Record<MapConfidenceLevel, string> = {
  not_enough_data: "Недостаточно данных", low_confidence: "Низкая надёжность",
  medium_confidence: "Средняя надёжность", high_confidence: "Высокая надёжность",
};

function unavailableReason(item: TeamMapComparisonItem, pool: TeamMapComparisonResponse): string {
  if (pool.aggregation_level === "current_roster" && (!pool.team_a.roster_id || !pool.team_b.roster_id)) return "Текущий состав не определён";
  if (item.comparison_status.includes("not_enough_data")) return "У одной или обеих команд меньше трёх карт";
  if (pool.aggregation_level === "current_roster") return "У текущего состава нет карт";
  return "У одной или обеих команд нет данных";
}

const h2hConfidence = { no_data: "Нет данных", low: "Низкая", medium: "Средняя", high: "Высокая" } as const;
const h2hSamples = { no_data: "Нет выборки", very_small: "Очень маленькая", small: "Маленькая", medium: "Средняя", sufficient: "Достаточная" } as const;
const applicabilityLabels = { direct: "прямая", high: "высокая", medium: "средняя", low: "низкая", unknown: "неизвестно" } as const;
const warningLabels: Record<string, string> = {
  very_small_sample: "Очень маленькая выборка", small_sample: "Маленькая выборка",
  stale_history: "История старше 180 дней", very_stale_history: "История старше года",
  partial_roster_data: "Не все исторические составы определены", excluded_invalid_maps: "Некорректные карты исключены",
  future_match_date: "Обнаружена будущая дата карты",
};

function dateLabel(value: string | null): string { return value ? new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU") : "—"; }
function numberLabel(value: number | null, suffix = ""): string { return value === null ? "—" : `${value.toFixed(2)}${suffix}`; }

function H2HSliceCard({ title, slice, h2h }: { title: string; slice: TeamH2HSlice; h2h: TeamH2HComparison }) {
  const unavailable = slice.status === "current_roster_unavailable";
  const empty = slice.status === "no_meetings" || slice.status === "current_rosters_never_met";
  return <article className="h2h-card">
    <div className="h2h-card__heading"><h3>{title}</h3><span className={`h2h-confidence h2h-confidence--${slice.confidence_level}`}>{h2hConfidence[slice.confidence_level]}</span></div>
    {unavailable ? <p>Невозможно определить H2H текущих составов: активная пятёрка одной из команд определена не полностью.</p>
      : empty ? <p>{slice.status === "no_meetings" ? "Очных карт организаций в сохранённых данных нет." : "Текущие составы ещё не встречались."}</p>
      : <>
        <div className="h2h-sides">
          {(["team_a", "team_b"] as const).map((side) => <div key={side}><strong>{h2h[side].name}</strong><b>{numberLabel(slice[side].h2h_rating)}</b><small>H2H-рейтинг / 100</small><span>Победы по картам: {slice[side].maps_won}</span><span>Раунды: {slice[side].rounds_won}</span><span>Winrate: {numberLabel(slice[side].map_win_rate, "%")}</span></div>)}
        </div>
        <dl className="h2h-meta"><div><dt>Серии</dt><dd>{slice.team_a_series_won}–{slice.team_b_series_won} · сыграно {slice.series_played}</dd></div><div><dt>Карты</dt><dd>{slice.team_a.maps_won}–{slice.team_b.maps_won} · сыграно {slice.maps_played}</dd></div><div><dt>Период</dt><dd>{dateLabel(slice.first_meeting_date)}–{dateLabel(slice.last_meeting_date)}</dd></div><div><dt>Надёжность</dt><dd>{h2hConfidence[slice.confidence_level]} · {slice.confidence_score.toFixed(2)}/100</dd></div><div><dt>Выборка</dt><dd>{h2hSamples[slice.sample_label]}</dd></div><div><dt>Преимущество</dt><dd>{slice.advantage_team_name ? `${slice.advantage_team_name} · ${slice.advantage_diff?.toFixed(2)}` : "Карты близки"}</dd></div></dl>
      </>}
    {title === "Текущие составы" && empty && <p className="formula">Roster #{h2h.team_a.current_roster_id ?? "—"} · roster #{h2h.team_b.current_roster_id ?? "—"}. Исторический H2H нельзя автоматически переносить на нынешние пятёрки.</p>}
    {slice.warnings.length > 0 && <div className="h2h-warnings">{slice.warnings.map((warning) => <span key={warning}>{warningLabels[warning] ?? warning}</span>)}</div>}
    {slice.maps.length > 0 && <details><summary>Статистика по картам</summary><div className="h2h-map-table"><div><b>Карта</b><b>Сыграно</b><b>{h2h.team_a.name}</b><b>{h2h.team_b.name}</b><b>Раунды</b><b>Последняя карта</b></div>{slice.maps.map((map) => <div key={map.map_name}><strong>{map.map_name}</strong><span>{map.maps_played}</span><span>{map.team_a_maps_won}</span><span>{map.team_b_maps_won}</span><span>{map.team_a_rounds_won}–{map.team_b_rounds_won}</span><span>{dateLabel(map.last_meeting_date)}</span></div>)}</div></details>}
    {slice.recent_maps.length > 0 && <details open><summary>Последние очные карты</summary><div className="h2h-recent">{slice.recent_maps.map((map) => <article key={map.demo_file_id}><span>{dateLabel(map.match_date)} · {map.tournament}</span><strong>{map.map_name} · {h2h.team_a.name} {map.team_a_score}:{map.team_b_score} {h2h.team_b.name}</strong><small>{map.went_to_overtime ? "Овертайм · " : ""}вес давности {map.recency_weight.toFixed(2)}</small><details><summary>Roster ID</summary><small>{map.team_a_roster_id ?? "не определён"} / {map.team_b_roster_id ?? "не определён"}</small></details></article>)}</div></details>}
  </article>;
}

function RosterContext({ name, opponent, context }: { name: string; opponent: string; context: TeamH2HRosterContext }) {
  const exp = context.experience, overlap = context.latest_roster_overlap;
  return <article><h4>{name}</h4>{exp.experience_data_status === "unavailable" ? <p>Недостаточно связанных player stats для оценки опыта игроков.</p> : <><p>{exp.players_with_h2h_experience_count} из {exp.current_players_count} текущих игроков уже играли против {opponent}.</p>{exp.experience_data_status === "partial" && <small>Данные player stats связаны не полностью; отсутствие опыта не гарантировано.</small>}</>}
    {overlap.status === "available" ? <p>{overlap.changed_players_count === 0 ? "Состав совпадает с последней очной картой." : `После последней очной карты заменено игроков: ${overlap.changed_players_count}.`}</p> : <p>Состав последней очной карты не определён полностью.</p>}</article>;
}

export function TeamComparePage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamA, setTeamA] = useState(0);
  const [teamB, setTeamB] = useState(0);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [loadingComparison, setLoadingComparison] = useState(false);
  const [comparison, setComparison] = useState<TeamComparison | null>(null);
  const [h2h, setH2H] = useState<TeamH2HComparison | null>(null);
  const [h2hLoading, setH2HLoading] = useState(false);
  const [h2hError, setH2HError] = useState<string | null>(null);
  const [mapPool, setMapPool] = useState<TeamMapComparisonResponse | null>(null);
  const [mapPoolLevel, setMapPoolLevel] = useState<"organization" | "current_roster">("current_roster");
  const [mapPoolLoading, setMapPoolLoading] = useState(false);
  const [mapPoolError, setMapPoolError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadComparison(a: number, b: number) {
    setLoadingComparison(true);
    setMapPoolLevel("current_roster");
    setMapPoolError(null);
    setError(null);
    setH2HLoading(true); setH2HError(null); setH2H(null);
    try {
      const [organization, maps] = await Promise.all([compareTeams(a, b), compareTeamMaps(a, b)]);
      setComparison(organization); setMapPool(maps);
    }
    catch (value: unknown) { setComparison(null); setError(value instanceof Error ? value.message : "Не удалось сравнить команды."); }
    finally { setLoadingComparison(false); }
    try { setH2H(await getTeamH2H(a, b)); }
    catch (value: unknown) { setH2HError(value instanceof Error ? value.message : "Не удалось загрузить H2H."); }
    finally { setH2HLoading(false); }
  }

  async function changeMapPoolLevel(level: "organization" | "current_roster") {
    setMapPoolLevel(level); setMapPoolLoading(true); setMapPoolError(null);
    try { setMapPool(await compareTeamMaps(teamA, teamB, level)); }
    catch (value: unknown) { setMapPool(null); setMapPoolError(value instanceof Error ? value.message : "Не удалось сравнить map pool."); }
    finally { setMapPoolLoading(false); }
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
        <section className="map-pool-comparison">
          <div className="section-heading"><div><p className="eyebrow">Аналитика карт</p><h2>Сравнение map pool</h2></div></div>
          <div className="roster-toggle"><button className={mapPoolLevel === "current_roster" ? "button button--primary" : "button"} onClick={() => void changeMapPoolLevel("current_roster")}>Текущие составы</button><button className={mapPoolLevel === "organization" ? "button button--primary" : "button"} onClick={() => void changeMapPoolLevel("organization")}>История организаций</button></div>
          {mapPoolLoading ? <div className="empty-state">Сравниваю карты…</div> : mapPoolError ? <div className="empty-state empty-state--error">{mapPoolError}</div> : !mapPool ? <div className="empty-state">Map pool ещё не загружен.</div> : mapPool.maps.length === 0 ? <div className="empty-state">{mapPool.status === "current_roster_unavailable" ? "Текущий состав одной из команд не определён." : mapPoolLevel === "current_roster" ? "У текущих составов пока нет карт." : "Для организаций пока нет агрегатов карт."}</div> : <>
            <div className="map-pool-table">
              <div className="map-pool-row map-pool-row--head"><span>Карта</span><span>{mapPool.team_a.name}</span><span>{mapPool.team_b.name}</span><span>Преимущество</span><span>Надёжность</span></div>
              {mapPool.maps.map((item) => <div className="map-pool-row" key={item.map_name}>
                <strong>{item.map_name[0].toUpperCase() + item.map_name.slice(1)}</strong>
                <span>{item.team_a?.map_strength_score === null || !item.team_a ? "—" : item.team_a.map_strength_score.toFixed(2)}<small>{item.team_a ? `${item.team_a.maps_won}–${item.team_a.maps_lost} · ${item.team_a.maps_played} карт` : "Нет данных"}</small>{item.team_a && <em className={`confidence-badge confidence-badge--${item.team_a.confidence_level}`}>{confidenceLabels[item.team_a.confidence_level]}</em>}</span>
                <span>{item.team_b?.map_strength_score === null || !item.team_b ? "—" : item.team_b.map_strength_score.toFixed(2)}<small>{item.team_b ? `${item.team_b.maps_won}–${item.team_b.maps_lost} · ${item.team_b.maps_played} карт` : "Нет данных"}</small>{item.team_b && <em className={`confidence-badge confidence-badge--${item.team_b.confidence_level}`}>{confidenceLabels[item.team_b.confidence_level]}</em>}</span>
                <span>{item.advantage_team_name ? <><b>{item.advantage_team_name}</b><small>+{item.advantage_diff?.toFixed(2)} · {item.advantage_level === "small" ? "небольшое" : item.advantage_level === "clear" ? "явное" : "сильное"}</small></> : item.comparison_status === "comparable" ? "Карты близки" : unavailableReason(item, mapPool)}</span>
                <span>{item.team_a && item.team_b ? `${item.team_a.confidence_score.toFixed(2)} / ${item.team_b.confidence_score.toFixed(2)}` : "—"}</span>
              </div>)}
            </div>
            <div className="map-pool-summary"><span>Преимущество {mapPool.team_a.name}: <b>{mapPool.summary.team_a_advantage_maps}</b></span><span>Преимущество {mapPool.team_b.name}: <b>{mapPool.summary.team_b_advantage_maps}</b></span><span>Близкие карты: <b>{mapPool.summary.close_maps}</b></span><span>Без достаточных данных: <b>{mapPool.summary.not_comparable_maps}</b></span></div>
          </>}
          <p className="formula">Сравнение описывает сохранённую статистику map pool и её надёжность. Это не прогноз результата матча или veto.</p>
        </section>
        <section className="h2h-section"><div className="section-heading"><div><p className="eyebrow">H2H-аналитика</p><h2>Личные встречи</h2></div></div>
          {h2hLoading ? <div className="empty-state">Загружаю очные карты…</div> : h2hError ? <div className="empty-state empty-state--error">{h2hError}</div> : h2h ? <>
            <div className="h2h-grid"><H2HSliceCard title="История организаций" slice={h2h.organizations} h2h={h2h} /><H2HSliceCard title="Текущие составы" slice={h2h.current_rosters} h2h={h2h} /></div>
            <div className="h2h-context"><div className="h2h-card__heading"><h3>Применимость истории к текущим составам</h3><span className={`h2h-applicability h2h-applicability--${h2h.roster_context.history_applicability}`}>{applicabilityLabels[h2h.roster_context.history_applicability]}</span></div><div className="h2h-context-grid"><RosterContext name={h2h.team_a.name} opponent={h2h.team_b.name} context={h2h.roster_context.team_a} /><RosterContext name={h2h.team_b.name} opponent={h2h.team_a.name} context={h2h.roster_context.team_b} /></div>{h2h.insights.length > 0 && <ul>{h2h.insights.map((insight, index) => <li key={`${insight.code}-${index}`}>{insight.text}</li>)}</ul>}</div>
          </> : <div className="empty-state">H2H ещё не загружен.</div>}
          <p className="formula">H2H описывает сохранённые очные карты и не является прогнозом результата будущей встречи.</p>
        </section>
        <section className="comparison-summary"><p className="eyebrow">Краткий вывод</p><h2>Что показывает сравнение</h2><ul>{comparison.summary_notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul></section>
      </> : !loadingTeams && teams.length >= 2 && !error ? <div className="empty-state">Выберите две команды для сравнения.</div> : null}
    </main>
  );
}
