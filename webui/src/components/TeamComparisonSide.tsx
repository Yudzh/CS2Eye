import type { TeamComparisonSide as ComparisonSide } from "../types";

const roleLabels: Record<string, string> = {
  igl: "IGL", awper: "AWPer", entry_frag: "Entry Frag",
  lurk: "Lurk", anchor_support: "Anchor / Support", rifler: "Rifler",
};

function formatDate(value: string | null) {
  if (!value) return "нет данных";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: value.includes("T") ? "short" : undefined,
  }).format(new Date(value));
}

export function TeamComparisonSide({ side }: { side: ComparisonSide }) {
  return (
    <article className="compare-side">
      <header className="compare-side__header">
        {side.logo_url ? <img src={side.logo_url} alt="" /> : <span>{side.name.slice(0, 2)}</span>}
        <div>
          <a href={`/teams/${side.id}`}><h2>{side.name}</h2></a>
          <p>{side.country_name || side.country_code || side.region || "Регион не указан"}</p>
        </div>
      </header>
      <div className="compare-metrics">
        <span><small>Место</small><strong>#{side.current_rank ?? "—"}</strong></span>
        <span><small>Очки</small><strong>{side.current_points === null ? "—" : Number(side.current_points).toFixed(1)}</strong></span>
        <span><small>Сила</small><strong>{side.strength.team_strength_score.toFixed(2)}<i>/100</i></strong></span>
        <span><small>В выбранной паре</small><strong>{side.relative_strength_percent === null ? "—" : `${side.relative_strength_percent.toFixed(2)}%`}</strong></span>
      </div>
      <p className="compare-disclaimer">Относительная сила в выбранной паре — не вероятность победы.</p>
      <dl className="compare-meta">
        <div><dt>Изменение позиции</dt><dd>{side.rank_change ?? "—"}</dd></div>
        <div><dt>Дата рейтинга</dt><dd>{formatDate(side.ranking_date)}</dd></div>
        <div><dt>Статус состава</dt><dd>{side.active_players_count === 5 ? "Полный" : `${side.active_players_count}/5 игроков`}</dd></div>
        <div><dt>Синхронизация</dt><dd>{formatDate(side.roster_synced_at)}</dd></div>
      </dl>
      <section className="compare-roster">
        <h3>Активный состав</h3>
        {side.roster.map((player) => (
          <a className="compare-player" href={`/players/${player.id}`} key={player.id}>
            {player.image_url ? <img src={player.image_url} alt="" /> : <span>{player.nickname.slice(0, 2)}</span>}
            <div><strong>{player.nickname}</strong><small>{player.role ? roleLabels[player.role] : "Роль не назначена"}</small></div>
            <b>{player.player_strength === null ? "—" : player.player_strength}<small>/100</small></b>
            <em>BO3: {player.bo3_rating === null ? "—" : Number(player.bo3_rating).toFixed(2)}</em>
            {player.strength_is_fallback && <mark>В расчёте использовано базовое значение 50</mark>}
          </a>
        ))}
        <div className="compare-coaches"><small>Тренер</small>{side.coaches.length ? side.coaches.map((coach) => <a href={`/players/${coach.id}`} key={coach.id}>{coach.nickname}</a>) : <span>не указан</span>}</div>
      </section>
      <section className="compare-strength-details">
        <h3>Расшифровка силы</h3>
        <p className="formula">{side.strength.calculation}</p>
        <div className="strength-totals"><span>Средняя: {side.strength.base_player_score.toFixed(2)}</span><span>Бонусы: +{side.strength.roster_bonus.toFixed(2)}</span><span>Штрафы: −{side.strength.roster_penalty.toFixed(2)}</span></div>
        {side.strength.factors.map((factor) => <div className="compare-factor" key={factor.code}><b>{factor.value > 0 ? "+" : ""}{factor.value.toFixed(2)}</b><span><strong>{factor.label}</strong><small>{factor.explanation}</small></span></div>)}
      </section>
    </article>
  );
}
