import {useEffect, useState} from "react";
import {getPredictionResults} from "../api";
import type {PredictionResult} from "../types";

const percent = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const versionsOf = (rows: PredictionResult[]) => [...new Set(rows.map(row => row.model_version))].sort((a, b) => b.localeCompare(a, undefined, {numeric: true}));

export function PredictionResultsPage() {
  const [rows, setRows] = useState<PredictionResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<PredictionResult["source"]>("pre_match");
  const [model, setModel] = useState("");
  const [tournament, setTournament] = useState("");
  const [outcome, setOutcome] = useState("");
  const [confidence, setConfidence] = useState("0");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null);
    getPredictionResults().then(data => {
      if (cancelled) return;
      const eligible = data.items.filter(row => row.source === "pre_match" || row.model_version === "v12");
      setRows(eligible);
      const initial = eligible.some(row => row.source === "pre_match") ? "pre_match" : "retrospective";
      setSource(initial);
      const versions = versionsOf(eligible.filter(row => row.source === initial));
      setModel(versions.includes(data.active_model_version ?? "") ? data.active_model_version! : versions[0] ?? "");
      setTournament(""); setOutcome(""); setConfidence("0"); setPage(1);
    }).catch(value => {if (!cancelled) setError(value instanceof Error ? value.message : "Не удалось загрузить результаты.");})
      .finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true;};
  }, [reload]);

  const sourced = rows.filter(row => row.source === source);
  const versions = versionsOf(sourced);
  const tournaments = [...new Map(sourced.filter(row => row.model_version === model).map(row => [String(row.tournament_id), row.tournament ?? "Без турнира"])).entries()];
  const selected = sourced.filter(row => row.model_version === model && (!tournament || String(row.tournament_id) === tournament) && (row.probability ?? 0) >= Number(confidence));
  const grade = (row: PredictionResult) => row.manual_adjustment ? row.archived_correct : row.correct;
  const graded = selected.filter(row => grade(row) != null);
  const correct = graded.filter(row => grade(row)).length;
  const visible = selected.filter(row => !outcome || (outcome === "hit" ? row.correct === true : outcome === "miss" ? row.correct === false : row.correct == null));
  const pages = Math.max(1, Math.ceil(visible.length / 25));
  const currentPage = Math.min(page, pages);

  return <main className="page prediction-results">
    <nav className="home-navigation"><a className="button" href="/">← Главная</a><a className="button" href="/matches">Матчи</a><a className="button" href="/prediction-history">Подробная история</a></nav>
    <header className="prediction-results__header"><div><p className="eyebrow">CS2Eye · прогнозы победителя</p><h1>Результаты прогнозов</h1><p>Наш выбор, результат матча и точность сохранённых прогнозов.</p></div><button className="button" disabled={loading} onClick={() => setReload(value => value + 1)}>Обновить</button></header>
    {loading ? <div className="empty-state" role="status">Загружаю результаты…</div> : error ? <div className="empty-state empty-state--error" role="alert">{error}<br/><button className="button" onClick={() => setReload(value => value + 1)}>Повторить</button></div> : <>
      <div className="prediction-results__sources">{([['pre_match', 'Сохранены до игры'], ['retrospective', 'Восстановлены по данным до игры']] as const).map(([key,label]) => <button className={`button${source === key ? " button--primary" : ""}`} key={key} onClick={() => {setSource(key); setModel(versionsOf(rows.filter(row => row.source === key))[0] ?? ""); setTournament(""); setPage(1);}}>{label}</button>)}</div>
      <p className="prediction-results__note">{source === "pre_match" ? "Прогнозы, сохранённые до игры, без пересчёта." : "Восстановленные прогнозы модели v12, обученной до последнего турнира. Расчёт выполнен после турнира по данным до даты каждой игры."}</p>
      <section className="prediction-results__filters" aria-label="Фильтры результатов">
        <label>Модель<select value={model} onChange={event => {setModel(event.target.value); setTournament(""); setPage(1);}}>{!versions.length && <option value="">Нет прогнозов</option>}{versions.map(version => <option key={version}>{version}</option>)}</select></label>
        <label>Турнир<select value={tournament} onChange={event => {setTournament(event.target.value); setPage(1);}}><option value="">Все турниры</option>{tournaments.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label>Уверенность<select value={confidence} onChange={event => {setConfidence(event.target.value); setPage(1);}}><option value="0">Любая</option>{[60, 70, 80, 90].map(value => <option key={value} value={value / 100}>От {value}%</option>)}</select></label>
        <label>Результат<select value={outcome} onChange={event => {setOutcome(event.target.value); setPage(1);}}><option value="">Все</option><option value="hit">Как и ожидали</option><option value="miss">Не зашло</option><option value="ungraded">Без выбора</option></select></label>
      </section>
      <section className="prediction-results__stats" aria-label="Статистика прогнозов">
        <div><small>Проверено</small><strong>{graded.length}</strong></div><div><small>Как и ожидали</small><strong className="prediction-results__hit">{correct}</strong></div><div><small>Не зашло</small><strong className="prediction-results__miss">{graded.length - correct}</strong></div><div><small>Точность</small><strong>{percent(graded.length ? correct / graded.length : null)}</strong></div>
      </section>
      <p className="prediction-results__note">Статистика для выбранных модели, турнира и уверенности. Фильтр «Результат» меняет только список. Прогнозы 50/50 не оцениваются. Поздние ручные поправки меняют показанный выбор, но не архивную точность.</p>
      {!visible.length ? <div className="empty-state">{!sourced.length ? "Завершённых матчей с сохранённым ML-прогнозом пока нет. Сохраняйте прогнозы до игры в сравнении команд." : "По выбранным фильтрам результатов нет."}</div> : <>
        <div className="prediction-results__list">{visible.slice((currentPage - 1) * 25, currentPage * 25).map(row => <article className="prediction-result" key={row.id}>
          <div className="prediction-result__match"><small>{row.tournament ?? "Без турнира"} · {new Date(`${row.match_date}T00:00:00Z`).toLocaleDateString("ru-RU", {timeZone: "UTC"})} · {row.format.toUpperCase()}</small><h2><a href={`/matches/${row.match_id}`}>{row.team_a.name} <span>{row.score.team_a} : {row.score.team_b}</span> {row.team_b.name}</a></h2><small>{row.model_version} · {source === "pre_match" ? "Сохранённый прогноз" : "Восстановленный прогноз"}</small></div>
          <div className="prediction-result__pick"><small>Наш прогноз</small><strong>{row.predicted_winner ?? "Без выбора · 50/50"}</strong><span>{percent(row.probability)}</span>{row.manual_adjustment&&<small>Модель: {percent(row.predicted_winner===row.team_a.name?row.manual_adjustment.base_team_a_probability:1-row.manual_adjustment.base_team_a_probability)} · Vitality +15 п.п.</small>}</div>
          <div className="prediction-result__actual"><small>Победитель</small><strong>{row.actual_winner}</strong></div>
          <span className={`prediction-result__badge prediction-result__badge--${row.correct == null ? "neutral" : row.correct ? "hit" : "miss"}`}>{row.correct == null ? "Без оценки" : row.manual_adjustment ? row.correct ? "✓ Выбор совпал" : "✕ Выбор не совпал" : row.correct ? "✓ Как и ожидали" : "✕ Не зашло"}</span>
        </article>)}</div>
        <div className="prediction-results__pagination"><button className="button" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>Назад</button><span>Страница {currentPage} из {pages} · {visible.length} прогнозов</span><button className="button" disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>Далее</button></div>
      </>}
    </>}
  </main>;
}
