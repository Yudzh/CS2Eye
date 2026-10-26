import {useEffect, useState} from "react";
import {getMatch} from "../api";
import type {MatchSeries} from "../types";
import {PandaScoreBinding} from "../components/PandaScoreBinding";

export function PandaScoreMatchPage({matchId}: {matchId: number}) {
  const [match, setMatch] = useState<MatchSeries | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {let active = true; getMatch(matchId).then(value => {if (active) setMatch(value);}).catch(error => {if (active) setError(error instanceof Error ? error.message : "Не удалось получить данные.");}); return () => {active = false;};}, [matchId]);
  return <main className="page matches-page"><a href={`/matches/${matchId}`}>← Наша карточка матча</a><header className="compare-heading"><p className="eyebrow">Источник привязки</p><h1>Матч из PandaScore</h1></header>{error && <p role="alert">{error}</p>}{match ? <><p>Наша карточка: <strong>{match.team_a.name} — {match.team_b.name}</strong> · {match.tournament?.name} · {match.starts_at ? new Date(match.starts_at).toLocaleString("ru-RU") : match.match_date}</p><PandaScoreBinding matchId={match.id} value={match.result_sync} expanded/>{match.result_sync?.error && <p role="alert">{match.result_sync.error}</p>}<p>Последняя проверка: {match.result_sync?.checked_at ? new Date(match.result_sync.checked_at).toLocaleString("ru-RU") : "ещё не выполнялась"}</p></> : !error && <p>Загружаю данные источника…</p>}</main>;
}
