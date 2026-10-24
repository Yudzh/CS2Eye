import {useEffect, useState} from "react";
import {getPredictionFeed} from "../api";
import type {PredictionFeedItem} from "../types";
import {ManualForecastButton} from "../components/ManualForecastButton";

const percent = (value: number | null) => value === null ? "—" : `${(value * 100).toFixed(1)}%`;
const dayLabel = (day: string) => new Date(`${day}T12:00:00`).toLocaleDateString("ru-RU", {day: "numeric", month: "long", year: "numeric"});
const today = () => new Date().toLocaleDateString("en-CA");
type Tab = "upcoming" | "completed";

function MatchPrediction({row, onCreated}: {row: PredictionFeedItem; onCreated: () => void}) {
  const p = row.team_a_probability;
  const played = row.status === "completed";
  return <article className={`forecast-row${played ? " forecast-row--played" : ""}`}>
    <div className="forecast-row__event"><span>{row.tournament ?? "Без турнира"}</span><small>{row.format.toUpperCase()}{row.status === "in_progress" ? " · Идёт матч" : row.starts_at ? ` · ${new Date(row.starts_at).toLocaleTimeString("ru-RU", {hour: "2-digit", minute: "2-digit"})}` : ""}</small></div>
    <a className="forecast-row__match" href={`/matches/${row.match_id}`} aria-label={`${row.team_a.name} — ${row.team_b.name}`}>
      <div className={p !== null && p > .5 ? "is-favorite" : ""}><strong>{row.team_a.name}</strong><span>{percent(p)}</span></div>
      <span className="forecast-row__score">{row.score ? `${row.score.team_a} : ${row.score.team_b}` : "VS"}</span>
      <div className={p !== null && p < .5 ? "is-favorite" : ""}><strong>{row.team_b.name}</strong><span>{percent(p === null ? null : 1 - p)}</span></div>
      {p !== null && <span className="forecast-row__bar" aria-hidden="true"><i style={{width: `${p * 100}%`}}/></span>}
    </a>
    <div className="forecast-row__pick"><small>Наш прогноз</small><strong>{p === null ? "Прогноз ещё не сохранён" : row.predicted_winner ?? "Равные шансы"}</strong><span>{p !== null && row.predicted_winner ? percent(row.probability) : p === null ? "Автосохранение повторит попытку" : "50 / 50"}</span>{p === null && <ManualForecastButton matchId={row.match_id} disabled={row.format === "unknown"} onCreated={onCreated}/>}</div>
    <div className="forecast-row__result">{played ? <><span className={`forecast-badge forecast-badge--${row.correct === null ? "neutral" : row.correct ? "hit" : "miss"}`}>{row.correct === null ? "Без оценки" : row.correct ? "✓ Угадали" : "✕ Не угадали"}</span><small>Победитель: {row.actual_winner ?? "не указан"}</small></> : <span className={`forecast-badge forecast-badge--${p === null ? "pending" : "neutral"}`}>{row.status === "in_progress" ? "Матч идёт" : p === null ? "Ожидает прогноза" : "Ожидает игры"}</span>}</div>
    <div className="forecast-row__footer"><span>{row.source === "retrospective" ? "Восстановленный прогноз" : row.source === "pre_match" ? "Сохранён до матча" : "Нет сохранённого прогноза"}{row.model_version ? ` · ${row.model_version}` : ""}</span>{row.captured_at && <time dateTime={row.captured_at}>Сохранён {new Date(row.captured_at).toLocaleString("ru-RU", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"})}</time>}<a href={`/matches/${row.match_id}`}>Разбор матча ↗</a></div>
  </article>;
}

export function PredictionsPage({initialTab = "upcoming"}: {initialTab?: Tab}) {
  const [tab, setTab] = useState<Tab>(() => new URLSearchParams(window.location.search).get("tab") === "completed" ? "completed" : initialTab);
  const [rows, setRows] = useState<PredictionFeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [search, setSearch] = useState("");
  const [tournament, setTournament] = useState("");
  const [day, setDay] = useState("");
  const [outcome, setOutcome] = useState("");
  const [limit, setLimit] = useState(30);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    getPredictionFeed().then(data => {if (active) setRows(data.items);})
      .catch(value => {if (active) setError(value instanceof Error ? value.message : "Не удалось загрузить прогнозы.");})
      .finally(() => {if (active) setLoading(false);});
    const timer = window.setInterval(() => setRefresh(value => value + 1), 60_000);
    return () => {active = false; window.clearInterval(timer);};
  }, [refresh]);
  function changeTab(value: Tab) {
    setTab(value); setOutcome(""); setLimit(30);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", value);
    window.history.replaceState(null, "", url);
  }
  const upcoming = rows.filter(row => row.status !== "completed");
  const completed = rows.filter(row => row.status === "completed");
  const tournaments = [...new Map(rows.map(row => [String(row.tournament_id), row.tournament ?? "Без турнира"])).entries()];
  const selected = (tab === "upcoming" ? upcoming : completed).filter(row =>
    (!tournament || String(row.tournament_id) === tournament) && (!day || row.match_date === day) &&
    (!search.trim() || `${row.team_a.name} ${row.team_b.name} ${row.tournament}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())));
  const official = selected.filter(row => row.source === "pre_match" && row.correct !== null);
  const hits = official.filter(row => row.correct).length;
  const replays = selected.filter(row => row.source === "retrospective" && row.correct !== null);
  const visible = selected.filter(row => !outcome || (outcome === "hit" ? row.correct === true : outcome === "miss" ? row.correct === false : row.source === "retrospective"))
    .sort((a, b) => tab === "upcoming" ? a.match_date.localeCompare(b.match_date) || (a.starts_at ?? "").localeCompare(b.starts_at ?? "") || a.match_id - b.match_id : b.match_date.localeCompare(a.match_date) || b.match_id - a.match_id);
  const groups = new Map<string, PredictionFeedItem[]>();
  visible.slice(0, limit).forEach(row => groups.set(row.match_date, [...(groups.get(row.match_date) ?? []), row]));
  const reset = () => {setSearch(""); setTournament(""); setDay(""); setOutcome(""); setLimit(30);};
  return <main className="page forecasts-page">
    <nav className="forecasts-nav" aria-label="Навигация"><a className="forecasts-brand" href="/">CS2<span>Eye</span></a><div><a className="is-active" href="/predictions" aria-current="page">Прогнозы</a><a href="/matches">Матчи</a><a href="/tournaments">Турниры</a><a href="/compare">Сравнение</a></div></nav>
    <header className="forecasts-heading"><div><p className="eyebrow">Матчи · вероятности · результаты</p><h1>Прогнозы</h1><p>Кого выбирает модель — и чем закончился матч.</p></div><button className="button" disabled={loading} onClick={() => setRefresh(value => value + 1)}>{loading ? "Обновляем…" : "Обновить"}</button></header>
    <div className="forecasts-tabs" role="tablist" aria-label="Матчи"><button role="tab" aria-selected={tab === "upcoming"} onClick={() => changeTab("upcoming")}>Предстоящие <span>{upcoming.length}</span></button><button role="tab" aria-selected={tab === "completed"} onClick={() => changeTab("completed")}>Сыгранные <span>{completed.length}</span></button></div>
    <section className="forecasts-toolbar" aria-label="Фильтры прогнозов"><label className="forecasts-search"><span>Поиск</span><input type="search" placeholder="Команда или турнир" value={search} onChange={e => {setSearch(e.target.value); setLimit(30);}}/></label><label><span>Турнир</span><select value={tournament} onChange={e => {setTournament(e.target.value); setLimit(30);}}><option value="">Все турниры</option>{tournaments.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select></label><label><span>Дата</span><input type="date" value={day} onChange={e => {setDay(e.target.value); setLimit(30);}}/></label>{tab === "completed" && <label><span>Результат</span><select value={outcome} onChange={e => {setOutcome(e.target.value); setLimit(30);}}><option value="">Все результаты</option><option value="hit">Угадали</option><option value="miss">Не угадали</option><option value="replay">Восстановленные</option></select></label>}{(search || tournament || day || outcome) && <button className="forecasts-reset" onClick={reset}>Сбросить</button>}</section>
    {error ? <div className="empty-state empty-state--error" role="alert">{error}<button className="button" onClick={() => setRefresh(value => value + 1)}>Повторить</button></div> : loading && !rows.length ? <div className="empty-state" role="status">Загружаем прогнозы…</div> : <>
      {tab === "completed" ? <section className="forecasts-summary" aria-label="Точность прогнозов"><div><span>Точность до матча</span><strong>{percent(official.length ? hits / official.length : null)}</strong><small>{hits} из {official.length} угадано</small></div><div><span>Восстановленные</span><strong>{percent(replays.length ? replays.filter(row => row.correct).length / replays.length : null)}</strong><small>{replays.length} прогнозов · отдельно от исходных</small></div><p>Вероятности берём из сохранённых прогнозов. Результаты матчей не меняют сделанный выбор.</p></section> : <p className="forecasts-context"><span className="forecasts-dot"/> Прогноз сохраняется автоматически, когда известны обе команды. <span>{selected.filter(row => row.team_a_probability !== null).length} из {selected.length} готовы</span></p>}
      <section aria-label={tab === "upcoming" ? "Предстоящие матчи" : "Сыгранные матчи"}>{!visible.length ? <div className="empty-state"><strong>{search || tournament || day || outcome ? "По этим фильтрам матчей нет" : tab === "upcoming" ? "Предстоящих матчей пока нет" : "Сыгранных матчей с прогнозами пока нет"}</strong><p>{search || tournament || day || outcome ? "Измените фильтры или сбросьте их." : tab === "upcoming" ? "Здесь появятся матчи, когда станут известны обе команды." : "После завершения игры здесь появятся счёт и результат прогноза."}</p></div> : [...groups].map(([date, matches]) => <section className="forecast-day" key={date}><h2>{date === today() ? "Сегодня" : dayLabel(date)}<span>{matches.length} матчей</span></h2>{matches.map(row => <MatchPrediction key={row.match_id} row={row} onCreated={() => setRefresh(value => value + 1)}/>)}</section>)}</section>
      {visible.length > limit && <button className="button forecasts-more" onClick={() => setLimit(value => value + 30)}>Показать ещё · осталось {visible.length - limit}</button>}
    </>}
    <footer className="forecasts-footer"><span>Один сохранённый выбор на матч. Восстановленные прогнозы отмечены в списке.</span><a href="/prediction-history">Подробная диагностика моделей ↗</a></footer>
  </main>;
}
