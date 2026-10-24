import {useEffect, useState} from "react";
import {capturePredictionHistory, getMatch, getPredictionHistory, getPredictionResults, getPredictionFeed} from "../api";
import type {MatchSeries, PredictionHistoryItem, PredictionResult, PredictionFeedItem} from "../types";
import {MatchCard} from "./MatchesPage";
import {ManualForecastButton} from "../components/ManualForecastButton";
const percent = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const outcome = (value: boolean | null) => value == null ? "Без оценки" : value ? "✓ Угадали" : "✕ Не угадали";
export function MatchDetailPage({matchId}: {matchId: number}) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [match, setMatch] = useState<MatchSeries | null>(null);
  const [history, setHistory] = useState<PredictionHistoryItem[]>([]);
  const [savedPick, setSavedPick] = useState<PredictionFeedItem | null>(null);
  const [results, setResults] = useState<PredictionResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setActionError(null); setMatch(null); setError(null); setPredictionError(null); setHistory([]); setResults([]); setSavedPick(null);
    async function load() {
      try {
        const value = await getMatch(matchId);
        if (!active) return;
        setMatch(value);
        let pick: PredictionFeedItem | undefined;
        if (value.status !== "completed") {
          try {
            const feed = await getPredictionFeed();
            pick = feed.items.find(item => item.match_id === matchId && item.team_a_probability !== null);
            if (active) setSavedPick(pick ?? null);
          } catch {
            if (active) setPredictionError("Не удалось загрузить часть прогнозов. Обновите страницу, чтобы повторить.");
          }
        }
        const beforeStart = value.starts_at ? new Date(value.starts_at).getTime() > Date.now() : value.match_date >= new Date().toLocaleDateString("en-CA");
        if (value.status === "scheduled" && !pick && beforeStart) {
          try {
            await capturePredictionHistory(matchId);
          } catch (error) {
            if (active) setActionError(error instanceof Error ? error.message : "Не удалось сохранить прогноз.");
          }
          if (!active) return;
        }
        const loaded = await Promise.allSettled([getPredictionHistory({tournamentId: value.tournament?.id, date: value.match_date, source: "pre_match"}), getPredictionResults()]);
        if (!active) return;
        if (loaded[0].status === "fulfilled") setHistory(loaded[0].value.items.filter(item => item.match_id === matchId && item.source === "pre_match"));
        if (loaded[1].status === "fulfilled") setResults(loaded[1].value.items.filter(item => item.match_id === matchId && (item.source === "pre_match" || item.model_version === "v12")));
        if (loaded.some(item => item.status === "rejected")) setPredictionError("Не удалось загрузить часть прогнозов. Обновите страницу, чтобы повторить.");
      } catch (value) { if (active) setError(value instanceof Error ? value.message : "Не удалось загрузить матч."); }
      finally { if (active) setLoading(false); }
    }
    void load(); return () => {active = false;};
  }, [matchId, refresh]);
  const winner = match?.winner_team_id == null ? null : match.winner_team_id === match.team_a.id ? match.team_a.name : match.winner_team_id === match.team_b.id ? match.team_b.name : null;
  return <main className="page matches-page"><nav className="page-links"><a className="back-link" href="/matches">← Все матчи</a><a href="/predictions">Все прогнозы</a></nav><header className="compare-heading"><p className="eyebrow">CS2Eye · карточка матча</p><h1>{match ? `${match.team_a.name ?? "Team A"} — ${match.team_b.name ?? "Team B"}` : "Карточка матча"}</h1></header>
    {error && <div className="empty-state empty-state--error" role="alert">{error}</div>}
    {match && <><section className="summary-grid"><article className="summary-card"><span>Результат серии</span><strong>{match.status === "scheduled" ? "Матч ещё не сыгран" : `${match.score.team_a} : ${match.score.team_b}`}</strong><small>{match.format.toUpperCase()}</small></article><article className="summary-card"><span>Победитель</span><strong>{winner ?? "Пока неизвестен"}</strong></article><article className="summary-card"><span>Турнир</span><strong>{match.tournament?.name ?? "Не указан"}</strong><small>{new Date(`${match.match_date}T00:00:00`).toLocaleDateString("ru-RU")}</small></article></section>
    {actionError && <p role="alert">{actionError}</p>}
    <section><h2>Сохранённые прогнозы</h2>
    <ManualForecastButton matchId={matchId} disabled={loading || match.team_a.id == null || match.team_b.id == null || match.format === "unknown"} onCreated={() => setRefresh(value => value + 1)}/>
    <p>После начала матча расчёт будет помечен как ретроспективный. Сохранённый предматчевый прогноз не перезаписывается.</p>
    {predictionError && <p role="alert">{predictionError}</p>}
    {savedPick && !results.length && <article className="strength-panel"><p className="eyebrow">{savedPick.source === "retrospective" ? "Восстановленный прогноз · данные до игры" : "Прогноз до матча"} · {savedPick.model_version}</p><h3>Наш прогноз: {savedPick.predicted_winner ?? "Без выбора · 50/50"} · {percent(savedPick.probability)}</h3><p>{savedPick.team_a.name}: {percent(savedPick.team_a_probability)} · {savedPick.team_b.name}: {percent(savedPick.team_a_probability === null ? null : 1 - savedPick.team_a_probability)}</p><p>Ожидает игры{savedPick.captured_at ? ` · Сохранён ${new Date(savedPick.captured_at).toLocaleString("ru-RU")}` : ""}</p></article>}
    {results.map(item => <article className="strength-panel" key={item.id}><p className="eyebrow">{item.source === "pre_match" ? "Прогноз до матча" : "Восстановленный прогноз · данные до игры"} · {item.model_version}</p><h3>Наш прогноз: {item.predicted_winner ?? "Без выбора · 50/50"} · {percent(item.probability)}</h3><p>{item.team_a.name}: {percent(item.team_a_probability)} · {item.team_b.name}: {percent(1 - item.team_a_probability)}</p><p>{outcome(item.correct)} · Сохранён {new Date(item.captured_at).toLocaleString("ru-RU")}</p>{item.manual_adjustment && <p>Ручная поправка: Vitality +15 п.п. Базовый прогноз модели: {item.team_a.name} {percent(item.manual_adjustment.base_team_a_probability)} · {item.team_b.name} {percent(1 - item.manual_adjustment.base_team_a_probability)}. Архивный результат: {outcome(item.archived_correct ?? null)}.</p>}</article>)}
    {history.map(item => <article className="strength-panel" key={item.id}><p className="eyebrow">{item.source === "pre_match" ? "Прогноз до матча" : "Исторический расчёт · не является предматчевым прогнозом"}</p><p>Сохранён {new Date(item.created_at).toLocaleString("ru-RU")} · Данные на {new Date(item.as_of).toLocaleString("ru-RU")}</p><div className="summary-grid">{([['team_strength', 'Team Strength'], ['matchup', 'Matchup'], ['ml', 'ML']] as const).map(([key, label]) => {const value = item[key]; return <article className="summary-card" key={key}><span>{label} · {item.versions[key] ?? "—"}</span><strong>{value.predicted_winner ?? "Нет сохранённого выбора"}</strong><p>{item.team_a.name}: {value.probability ? percent(value.team_a_value) : value.team_a_value?.toFixed(1) ?? "—"}<br/>{item.team_b.name}: {value.probability ? percent(value.team_b_value) : value.team_b_value?.toFixed(1) ?? "—"}</p><small>{value.probability ? "Вероятность победы" : "Оценка силы"} · {item.source === "retrospective" ? "Без оценки · исторический расчёт" : outcome(value.correct)}</small></article>})}</div>{!!item.error_analysis?.matchup.factors.length && <details><summary>Факторы прогноза Matchup</summary>{item.error_analysis.matchup.factors.map(factor => <p key={factor.factor}>{factor.label}: {factor.contribution > 0 ? "+" : ""}{factor.contribution.toFixed(2)} · надёжность {percent(factor.reliability)}</p>)}</details>}</article>)}
    {!loading && !history.length && !results.length && !savedPick && !predictionError && <div className="empty-state"><strong>Сохранённого прогноза для этого матча нет.</strong>{match.prediction_history_coverage && match.prediction_history_coverage.teams.some(team => team.available_maps < match.prediction_history_coverage!.required_maps) && <><p>Для расчёта не хватает исторических данных до {new Date(`${match.prediction_history_coverage.as_of}T00:00:00`).toLocaleDateString("ru-RU")}.</p>{match.prediction_history_coverage.teams.filter(team => team.available_maps < match.prediction_history_coverage!.required_maps).map((team, index) => <p key={team.team_id ?? index}>{team.name ?? "Неизвестная команда"}: доступно {team.available_maps} карт с полной статистикой раундов, требуется минимум {match.prediction_history_coverage!.required_maps}.</p>)}<small>Нужны демки более ранних игр этих команд. Карты после даты матча не учитываются.</small></>}</div>}</section><section><h2>Карты и veto</h2><MatchCard match={match}/></section></>}
    {loading && <div className="empty-state" role="status">Загружаю карточку матча…</div>}
  </main>;
}
