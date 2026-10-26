import type {ResultSync} from "../types";

export function PandaScoreBinding({matchId, value, expanded = false}: {matchId: number; value?: ResultSync | null; expanded?: boolean}) {
  if (!value?.external_id) return <div className="pandascore-binding pandascore-binding--pending"><strong>PandaScore: матч ещё не привязан</strong><small>Сопоставление появится после проверки или ручной привязки.</small></div>;
  const match = value.provider_match;
  const verified = !!match && value.status !== "needs_review" && value.status !== "linked" && value.status !== "error";
  return <div className={`pandascore-binding ${verified ? "pandascore-binding--verified" : "pandascore-binding--pending"}`}>
    <div className="pandascore-binding__head"><strong>{verified ? "✓ Данные PandaScore получены" : "Привязка требует проверки"}</strong><a href={`/matches/${matchId}/pandascore`} target="_blank" rel="noopener noreferrer">Матч PandaScore #{value.external_id} ↗</a></div>
    {!match ? <p>Внешний ID сохранён, но данные матча ещё не получены. Нажмите «Проверить результат».</p> : <>
      <h4>{match.opponents.map(team => team.name ?? `Команда #${team.id}`).join(" — ")}</h4>
      <p>{[match.league.name, match.serie.full_name ?? match.serie.name, match.tournament.name].filter(Boolean).join(" → ")}</p>
      <div className="pandascore-binding__facts"><span>Начало PandaScore: <b>{match.begin_at ? new Date(match.begin_at).toLocaleString("ru-RU") : "не указано"}</b></span><span>Статус источника: <b>{match.status}</b></span>
      {match.opponents.map(team => <span key={team.id}>{team.name} <small>#{team.id}</small>{match.results?.some(score => score?.team_id === team.id) && <b> · {match.results.find(score => score?.team_id === team.id)?.score} карт</b>}</span>)}</div>
      {value.link && <small>Наша команда → PandaScore: {Object.entries(value.link).map(([local, external]) => `#${local} → #${external}`).join(" · ")}</small>}
      {expanded && <><p>Это последние данные, полученные сервером из PandaScore. Сверьте команды, событие и время с нашей карточкой.</p><p><a href={value.provider_api_url ?? undefined} target="_blank" rel="noopener noreferrer">Исходный запрос PandaScore API ↗</a></p><small>API требует вашу авторизацию. Серверный токен в ссылку не включается и браузеру не передаётся.</small></>}
    </>}
  </div>;
}
