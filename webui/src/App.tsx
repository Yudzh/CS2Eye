import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getLatestRun,
  getTeams,
  getTeam,
  updatePlayerRole,
  probeTopTeams,
  refreshTopTeams,
  getPlayer,
  refreshPlayer,
  getTeamMaps,
  getTeamMapDetail,
} from "./api";
import type {
  ProbeResult,
  RankingRun,
  Team,
  TeamDetail,
  TeamParticipant,
  Player,
  TeamMapAggregate,
  TeamMapScope,
  TeamMapDetail,
} from "./types";
import { TeamComparePage } from "./pages/TeamComparePage";
import { DemosPage } from "./pages/DemosPage";


type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; message: string };

type ActionState =
  | { kind: "idle" }
  | { kind: "probing" }
  | { kind: "refreshing" }
  | {
      kind: "success";
      message: string;
    }
  | { kind: "error"; message: string };


function RosterGroup({
  label,
  members,
}: {
  label: string;
  members: TeamParticipant[];
}) {
  if (!members.length) {
    return null;
  }
  return (
    <div className="roster-group">
      <small>{label}</small>
      <div className="roster__members">
        {members.map((participant) => (
          <a
            className="roster-member"
            key={`${participant.participant_type}-${participant.bo3_id}`}
            title={participant.country_name || undefined}
            href={`/players/${participant.id}`}
          >
            {participant.image_url && (
              <img alt="" src={participant.image_url} />
            )}
            <span>{participant.nickname}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function TeamCard({ team }: { team: Team }) {
  const players = team.roster.filter(
    (participant) => participant.participant_type === "player",
  );
  const substitutes = team.roster.filter(
    (participant) => participant.participant_type === "substitute",
  );
  const coaches = team.roster.filter(
    (participant) => participant.participant_type === "coach",
  );

  return (
    <article className="team-card">
      <header className="team-card__header">
        <span className="team-card__rank">
          <small>место</small>
          <strong>#{team.current_rank ?? "—"}</strong>
        </span>
        <div className="team-card__state">
          {!team.is_analytics_active && (
            <span className="analytics-status">Не считаем</span>
          )}
          <span
            className={
              team.rank_change && team.rank_change !== 0
                ? team.rank_change > 0
                  ? "change change--up"
                  : "change change--down"
                : "change"
            }
          >
            {rankChangeLabel(team.rank_change)}
          </span>
        </div>
      </header>

      <div className="team-card__identity">
        {team.logo_url ? (
          <img alt="" src={team.logo_url} />
        ) : (
          <span className="team-card__logo-placeholder">
            {team.name.slice(0, 2)}
          </span>
        )}
        <div>
          <h3><a href={`/teams/${team.id}`}>{team.name}</a></h3>
          <span>
            {team.country_name || team.country_code || team.region || "Регион не указан"}
          </span>
        </div>
      </div>

      <div className="team-card__stats">
        <span>
          <small>Очки Valve</small>
          <strong>{formatPoints(team.current_points)}</strong>
        </span>
        <span>
          <small>Игроки</small>
          <strong>{players.length || "—"}</strong>
        </span>
      </div>

      <div className="team-card__roster">
        {team.roster.length ? (
          <>
            <RosterGroup label="Основной состав" members={players} />
            <RosterGroup label="Запасные" members={substitutes} />
            <RosterGroup label="Тренеры" members={coaches} />
          </>
        ) : (
          <span className="roster__empty">состав не синхронизирован</span>
        )}
      </div>

      <footer className="team-card__footer">
        <span>{team.bo3_slug}</span>
        <span>Синхронизация: {formatDate(team.roster_synced_at)}</span>
      </footer>
    </article>
  );
}

function PlayerPage({ id }: { id: number }) {
  const [player, setPlayer] = useState<Player | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    getPlayer(id).then(setPlayer).catch((value: unknown) => {
      setError(value instanceof Error ? value.message : "Не удалось загрузить игрока.");
    });
  }, [id]);

  const update = async () => {
    setRefreshing(true);
    setError(null);
    try {
      setPlayer(await refreshPlayer(id));
    } catch (value: unknown) {
      setError(value instanceof Error ? value.message : "Не удалось обновить игрока.");
    } finally {
      setRefreshing(false);
    }
  };

  if (error && !player) return <main className="page"><a href="/">← К командам</a><div className="empty-state empty-state--error">{error}</div></main>;
  if (!player) return <main className="page"><div className="empty-state">Загружаю игрока…</div></main>;
  const currentTeam = player.teams.find((team) => team.is_active);
  const fullName = [player.first_name, player.last_name].filter(Boolean).join(" ");
  return (
    <main className="page player-page">
      <a className="back-link" href="/">← К составам команд</a>
      <section className="player-hero">
        {player.image_url ? <img className="player-photo" src={player.image_url} alt={player.nickname} /> : <div className="player-photo player-photo--empty">{player.nickname.slice(0, 2)}</div>}
        <div className="player-heading">
          <p className="eyebrow">Игрок · BO3.gg</p>
          <h1>{player.nickname}</h1>
          <p className="lead">{fullName || "Настоящее имя не указано"} · {player.country_name || player.country_code || "страна не указана"}</p>
          <div className="player-team-status">
            <strong>{currentTeam?.name || player.teams[0]?.name || "Без команды"}</strong>
            <span className={currentTeam ? "status-active" : "status-former"}>{currentTeam ? "активный игрок команды" : "бывший игрок команды"}</span>
          </div>
        </div>
        <button className="button button--primary" disabled={refreshing} onClick={() => void update()}>{refreshing ? "Обновляю…" : "Обновить из BO3.gg"}</button>
      </section>
      {error && <div className="notice notice--error">{error}</div>}
      <section className="player-grid">
        <article className="metric-card"><span>Avg BO3.gg</span><strong>{player.bo3_avg_rating === null ? "—" : Number(player.bo3_avg_rating).toFixed(2)}</strong></article>
        <article className="metric-card internal-rating-card" title="Группа соперника определяется по его месту на дату матча. Если исторических данных нет, используется текущее место."><span>Внутренний рейтинг</span>{[["Общий", player.internal_rating, player.internal_rating_maps_count, player.internal_rating_rounds_count], ["Против Top 1–15", player.internal_rating_top15, player.internal_rating_top15_maps_count, player.internal_rating_top15_rounds_count], ["Против Top 16–30", player.internal_rating_top16_30, player.internal_rating_top16_30_maps_count, player.internal_rating_top16_30_rounds_count]].map(([label, rating, maps, rounds]) => <div className="internal-rating-row" key={String(label)}><span>{label}</span><strong>{rating === null ? "—" : Number(rating).toFixed(2)}</strong><small>{rating === null ? "Нет данных" : `${maps} карт · ${rounds} раундов`}</small></div>)}</article>
        <article className="metric-card"><span>Сила игрока</span><strong>{player.player_strength ?? "—"}<small>/100</small></strong></article>
        <article className="metric-card"><span>Последнее обновление</span><strong className="metric-date">{formatDate(player.stats_synced_at)}</strong></article>
      </section>
      <section className="strength-panel">
        <div className="section-heading"><div><p className="eyebrow">Расшифровка</p><h2>Что повлияло на силу</h2></div></div>
        {player.strength_breakdown ? player.strength_breakdown.factors.map((factor) => (
          <div className="factor" key={factor.metric}><span className={`factor__impact factor__impact--${factor.direction}`}>{factor.impact > 0 ? "+" : ""}{factor.impact}</span><div><strong>Avg BO3.gg: {factor.value.toFixed(2)}</strong><p>{factor.explanation}</p></div></div>
        )) : <div className="empty-state">BO3.gg пока не предоставил рейтинг. Нажмите «Обновить».</div>}
        {player.strength_breakdown && <small className="formula">{player.strength_breakdown.formula}</small>}
      </section>
    </main>
  );
}


const roleLabels: Record<string, string> = {
  igl: "IGL",
  awper: "AWPer",
  entry_frag: "Entry frag",
  lurk: "Lurk",
  anchor_support: "Anchor / Support",
  rifler: "Rifler",
};

function TeamPage({ id }: { id: number }) {
  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [savingPlayerId, setSavingPlayerId] = useState<number | null>(null);
  const [mapStats, setMapStats] = useState<TeamMapAggregate[]>([]);
  const [mapFilter, setMapFilter] = useState("all");
  const [mapSort, setMapSort] = useState("maps");
  const [mapDetails, setMapDetails] = useState<Record<string, TeamMapDetail>>({});
  const [aggregationLevel, setAggregationLevel] = useState<"organization" | "current_roster">("current_roster");

  useEffect(() => {
    getTeam(id).then(setTeam).catch((value: unknown) => {
      setError(value instanceof Error ? value.message : "Не удалось загрузить команду.");
    });
  }, [id]);

  useEffect(() => {
    setMapDetails({});
    getTeamMaps(id, aggregationLevel).then((value) => setMapStats(value.maps)).catch(() => setMapStats([]));
  }, [id, aggregationLevel]);

  if (error) return <main className="page"><a className="back-link" href="/">← К командам</a><div className="empty-state empty-state--error">{error}</div></main>;
  if (!team) return <main className="page"><div className="empty-state">Загружаю команду…</div></main>;

  const activePlayers = team.roster.filter(
    (member) => member.participant_type === "player" && member.is_active && !member.left_at,
  );
  const coaches = team.roster.filter(
    (member) => member.participant_type === "coach" && member.is_active && !member.left_at,
  );
  const strength = team.strength;
  const visibleMaps = mapStats.filter((item) => {
    if (mapFilter === "min3") return item.all.maps_played >= 3;
    if (mapFilter === "min5") return item.all.maps_played >= 5;
    if (mapFilter === "fresh") return item.all.freshness_label === "fresh";
    return true;
  }).sort((a, b) => {
    if (mapSort === "winrate") return (b.all.map_win_rate ?? -1) - (a.all.map_win_rate ?? -1);
    if (mapSort === "ct") return (b.all.ct.win_rate ?? -1) - (a.all.ct.win_rate ?? -1);
    if (mapSort === "t") return (b.all.t.win_rate ?? -1) - (a.all.t.win_rate ?? -1);
    if (mapSort === "date") return (b.all.last_match_date ?? "").localeCompare(a.all.last_match_date ?? "");
    return b.all.maps_played - a.all.maps_played;
  });

  async function changeRole(
    playerId: number,
    role: TeamParticipant["role"],
  ) {
    setSavingPlayerId(playerId);
    setRoleError(null);
    try {
      setTeam(await updatePlayerRole(id, playerId, role));
    } catch (value: unknown) {
      setRoleError(
        value instanceof Error ? value.message : "Не удалось сохранить роль.",
      );
    } finally {
      setSavingPlayerId(null);
    }
  }

  function loadMapDetail(mapName: string) {
    if (mapDetails[mapName]) return;
    void getTeamMapDetail(id, mapName, aggregationLevel).then((value) => {
      setMapDetails((current) => ({ ...current, [mapName]: value }));
    });
  }

  return (
    <main className="page team-page">
      <nav className="page-links"><a className="back-link" href="/">← К командам</a><a className="back-link" href={`/compare?team_a=${team.id}`}>Сравнение команд →</a></nav>
      <section className="team-hero">
        {team.logo_url ? <img src={team.logo_url} alt="" /> : <div className="team-hero__logo">{team.name.slice(0, 2)}</div>}
        <div>
          <p className="eyebrow">Карточка команды · #{team.current_rank ?? "—"}</p>
          <h1>{team.name}</h1>
          <p className="lead">{team.country_name || team.country_code || team.region || "Регион не указан"}</p>
        </div>
        <div className="team-strength-score"><small>Сила команды</small><strong>{strength.team_strength_score.toFixed(2)}</strong><span>/100</span></div>
      </section>

      <section className="team-metrics">
        <article className="metric-card"><span>Активных игроков</span><strong>{strength.active_players_count}<small>/5</small></strong></article>
        <article className="metric-card"><span>Средняя сила игроков</span><strong>{strength.base_player_score.toFixed(2)}</strong></article>
        <article className="metric-card"><span>Бонус / штраф</span><strong className="metric-adjustment">+{strength.roster_bonus.toFixed(2)} / −{strength.roster_penalty.toFixed(2)}</strong></article>
      </section>

      <section className="strength-panel team-map-panel">
        <div className="section-heading"><div><p className="eyebrow">Аналитика</p><h2>Статистика по картам</h2></div></div>
        <div className="team-map-controls">
          <div className="roster-toggle"><button className={aggregationLevel === "current_roster" ? "button button--primary" : "button"} onClick={() => setAggregationLevel("current_roster")}>Текущий состав</button><button className={aggregationLevel === "organization" ? "button button--primary" : "button"} onClick={() => setAggregationLevel("organization")}>История организации</button></div>
          <select value={mapFilter} onChange={(event) => setMapFilter(event.target.value)}><option value="all">Все карты</option><option value="min3">Минимум 3 карты</option><option value="min5">Минимум 5 карт</option><option value="fresh">Только свежие</option></select>
          <select value={mapSort} onChange={(event) => setMapSort(event.target.value)}><option value="maps">По числу карт</option><option value="winrate">По winrate</option><option value="date">По последней дате</option><option value="ct">По CT winrate</option><option value="t">По T winrate</option></select>
        </div>
        {visibleMaps.length === 0 ? <div className="empty-state">{aggregationLevel === "current_roster" ? "У текущего состава ещё нет сыгранных карт." : "По картам ещё нет полностью распарсенных демок."}</div> : <div className="team-map-grid">{visibleMaps.map((item) => {
          const percent = (value: number | null) => value === null ? "—" : `${value.toFixed(1)}%`;
          const record = (scope: TeamMapScope | null | undefined) => scope ? `${scope.maps_won}–${scope.maps_lost}` : "—";
          const detail = mapDetails[item.map_name];
          return <details className="team-map-card" key={item.map_name} onToggle={(event) => event.currentTarget.open && loadMapDetail(item.map_name)}>
            <summary><strong>{item.map_name[0].toUpperCase() + item.map_name.slice(1)}</strong><span>{item.all.maps_won}–{item.all.maps_lost} · {percent(item.all.map_win_rate)}</span></summary>
            <div className="team-map-rates"><span>CT <strong>{percent(item.all.ct.win_rate)}</strong></span><span>T <strong>{percent(item.all.t.win_rate)}</strong></span><span>Раунды <strong>{item.all.rounds_won}–{item.all.rounds_lost}</strong></span></div>
            <div className="team-map-scopes"><span>Последние 5: <b>{record(item.recent.last_5)}</b></span><span>Последние 10: <b>{record(item.recent.last_10)}</b></span><span>Последние 20: <b>{record(item.recent.last_20)}</b></span><span>Top 15: <b>{record(item.versus.top_15)}</b></span><span>Top 16–30: <b>{record(item.versus.top_16_30)}</b></span><span>Тир 2–3: <b>{record(item.versus.tier_2_3)}</b></span></div>
            <small>{item.all.maps_played} карт · Последняя: {item.all.last_match_date ? new Date(item.all.last_match_date).toLocaleDateString("ru-RU") : "дата неизвестна"} · Выборка: {item.all.sample_size_label} · Свежесть: {item.all.freshness_label}</small>
            {item.all.maps_played <= 2 && <p className="map-warning">Недостаточная выборка — выводы ненадёжны.</p>}
            {item.all.freshness_label === "very_stale" && <p className="map-warning">Последняя карта сыграна более 90 дней назад.</p>}
            {detail && <div className="team-map-matches"><b>{aggregationLevel === "current_roster" ? "Последние игры текущего состава" : "Последние карты организации"}</b>{detail.recent_matches.map((match) => <div key={match.demo_file_id}><span>{match.match_date ? new Date(match.match_date).toLocaleDateString("ru-RU") : "Дата неизвестна"}</span><span>{match.opponent_team_name ?? "Неизвестный соперник"}{match.opponent_rank ? ` (#${match.opponent_rank})` : ""}</span><strong className={match.result === "win" ? "match-win" : "match-loss"}>{match.score_for}:{match.score_against}</strong></div>)}</div>}
          </details>;
        })}</div>}
        <p className="formula">Оценка выборки зависит от количества распарсенных карт и не является оценкой силы команды. Свежесть рассчитывается по дате последней карты.</p>
      </section>

      <section className="team-detail-grid">
        <article className="strength-panel team-roster-panel">
          <div className="section-heading"><div><p className="eyebrow">Ростер</p><h2>Игроки</h2></div><span>{activePlayers.length} активных</span></div>
          <div className="team-player-list">
            {activePlayers.map((player) => (
              <div className="team-player-card" key={player.id}>
                {player.image_url ? <img src={player.image_url} alt="" /> : <span>{player.nickname.slice(0, 2)}</span>}
                <div><a href={`/players/${player.id}`}><strong>{player.nickname}</strong></a><small>{player.role ? roleLabels[player.role] : "Роль не назначена"}</small></div>
                <label className="role-picker">
                  <span>Роль</span>
                  <select
                    value={player.role ?? ""}
                    disabled={savingPlayerId === player.id}
                    onChange={(event) => void changeRole(
                      player.id,
                      (event.target.value || null) as TeamParticipant["role"],
                    )}
                  >
                    <option value="">Не назначена</option>
                    {Object.entries(roleLabels).map(([value, label]) => (
                      <option value={value} key={value}>{label}</option>
                    ))}
                  </select>
                </label>
                <div className="player-ratings"><span><small>Avg BO3.gg</small>{player.bo3_avg_rating === null ? "—" : Number(player.bo3_avg_rating).toFixed(2)}</span><span className="compact-internal" title={`Общий: ${player.internal_rating_maps_count} карт, ${player.internal_rating_rounds_count} раундов; Top 15: ${player.internal_rating_top15_maps_count} карт, ${player.internal_rating_top15_rounds_count} раундов; Top 16–30: ${player.internal_rating_top16_30_maps_count} карт, ${player.internal_rating_top16_30_rounds_count} раундов`}><small>Внутренний</small>{player.internal_rating === null ? "—" : Number(player.internal_rating).toFixed(2)}<em>Top 15: {player.internal_rating_top15 === null ? "—" : Number(player.internal_rating_top15).toFixed(2)} · Top 16–30: {player.internal_rating_top16_30 === null ? "—" : Number(player.internal_rating_top16_30).toFixed(2)}</em></span><span><small>Сила</small>{player.player_strength ?? "—"}</span></div>
              </div>
            ))}
          </div>
          {roleError && <div className="empty-state empty-state--error">{roleError}</div>}
          <div className="coach-list"><small>Тренер</small>{coaches.length ? coaches.map((coach) => <a href={`/players/${coach.id}`} key={coach.id}>{coach.nickname}</a>) : <span>не указан</span>}</div>
        </article>

        <article className="strength-panel team-factors-panel">
          <div className="section-heading"><div><p className="eyebrow">Расчёт силы</p><h2>{strength.calculation}</h2></div></div>
          {strength.factors.map((factor) => (
            <div className="team-factor" key={factor.code}>
              <span className={`team-factor__value team-factor__value--${factor.kind}`}>{factor.value > 0 && factor.kind !== "base" ? "+" : ""}{factor.value.toFixed(2)}</span>
              <div><strong>{factor.label}</strong><p>{factor.explanation}</p>{factor.players.length > 0 && <small>{factor.players.join(", ")}</small>}</div>
            </div>
          ))}
          {strength.notes.length > 0 && <ul className="strength-notes">{strength.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
        </article>
      </section>
    </main>
  );
}

function formatPoints(
  value: Team["current_points"],
): string {
  if (value === null) {
    return "—";
  }
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 1,
  }).format(Number(value));
}


function formatDate(value: string | null): string {
  if (!value) {
    return "ещё не запускалось";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: value.includes("T")
      ? "short"
      : undefined,
  }).format(new Date(value));
}


function rankChangeLabel(
  value: number | null,
): string {
  if (value === null) {
    return "нет данных";
  }
  if (value > 0) {
    return `↑ ${value}`;
  }
  if (value < 0) {
    return `↓ ${Math.abs(value)}`;
  }
  return "без изменений";
}


export default function App() {
  if (/^\/demos\/?$/.test(window.location.pathname)) return <DemosPage />;
  if (/^\/compare\/?$/.test(window.location.pathname)) return <TeamComparePage />;
  const playerMatch = window.location.pathname.match(/^\/players\/(\d+)\/?$/);
  if (playerMatch) return <PlayerPage id={Number(playerMatch[1])} />;
  const teamMatch = window.location.pathname.match(/^\/teams\/(\d+)\/?$/);
  if (teamMatch) return <TeamPage id={Number(teamMatch[1])} />;
  const [teams, setTeams] = useState<Team[]>([]);
  const [latestRun, setLatestRun] =
    useState<RankingRun | null>(null);
  const [loadState, setLoadState] =
    useState<LoadState>({ kind: "loading" });
  const [actionState, setActionState] =
    useState<ActionState>({ kind: "idle" });
  const [probe, setProbe] =
    useState<ProbeResult | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [teamPayload, runPayload] =
        await Promise.all([
          getTeams(),
          getLatestRun(),
        ]);
      setTeams(teamPayload);
      setLatestRun(runPayload);
      setLoadState({ kind: "ready" });
    } catch (error: unknown) {
      setLoadState({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Не удалось загрузить данные.",
      });
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleProbe = async () => {
    setActionState({ kind: "probing" });
    setProbe(null);

    try {
      const payload = await probeTopTeams();
      setProbe(payload);
      setActionState({
        kind: "success",
        message:
          `BO3.gg вернул ${payload.teams_received}`
          + " корректных команд. БД не изменена.",
      });
    } catch (error: unknown) {
      setActionState({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Проверка BO3.gg завершилась ошибкой.",
      });
    }
  };

  const handleRefresh = async () => {
    setActionState({ kind: "refreshing" });

    try {
      const run = await refreshTopTeams();
      setActionState({
        kind: "success",
        message:
          "Top-40 обновлён; места 31–40 сохранены как теневые. "
          + `Активировано: ${run.teams_activated}, `
          + `деактивировано: ${run.teams_deactivated}. `
          + `Профили: ${run.player_profiles_updated} успешно, `
          + `${run.player_profiles_failed} с ошибкой.`,
      });
      await loadData();
      setLatestRun(run);
    } catch (error: unknown) {
      setActionState({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Обновление завершилось ошибкой.",
      });
      await loadData();
    }
  };

  const actionInProgress =
    actionState.kind === "probing"
    || actionState.kind === "refreshing";

  return (
    <main className="page">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">C2</span>
          <div>
            <strong>CS2Eye</strong>
            <span>аналитический top‑30</span>
          </div>
        </div>

        <span className="source-badge">
          источник: BO3.gg
        </span>
      </header>

      <nav className="home-navigation"><a className="button" href="/demos">Демки</a><a className="button" href="/compare">Сравнение команд</a></nav>

      <section className="hero">
        <div>
          <p className="eyebrow">
            Итерация 01 · команды
          </p>
          <h1>Valve World Top‑30</h1>
          <p className="lead">
            В аналитике участвуют только команды
            текущего рейтинга. Выбывшие команды
            остаются в базе, но автоматически
            становятся неактивными.
          </p>
        </div>

        <div className="hero__actions">
          <button
            className="button button--ghost"
            disabled={actionInProgress}
            onClick={() => {
              void handleProbe();
            }}
            type="button"
          >
            {actionState.kind === "probing"
              ? "Проверяю…"
              : "Проверить BO3.gg"}
          </button>
          <button
            className="button button--primary"
            disabled={actionInProgress}
            onClick={() => {
              void handleRefresh();
            }}
            type="button"
          >
            {actionState.kind === "refreshing"
              ? "Обновляю…"
              : "Обновить всё"}
          </button>
        </div>
      </section>

      <section className="summary-grid">
        <article className="summary-card">
          <span>Активные команды</span>
          <strong>{teams.filter((team) => team.is_analytics_active).length}</strong>
          <small>ожидается ровно 30</small>
        </article>
        <article className="summary-card">
          <span>Дата рейтинга</span>
          <strong className="summary-card__date">
            {formatDate(
              latestRun?.ranking_date || null,
            )}
          </strong>
          <small>Valve World Ranking</small>
        </article>
        <article className="summary-card">
          <span>Последнее обновление</span>
          <strong className="summary-card__date">
            {formatDate(
              latestRun?.finished_at || null,
            )}
          </strong>
          <small>
            {latestRun?.status === "failed"
              ? "ошибка импорта"
              : "ручной запуск"}
          </small>
        </article>
      </section>

      {actionState.kind !== "idle" && (
        <div
          className={
            actionState.kind === "error"
              ? "notice notice--error"
              : "notice"
          }
          role="status"
        >
          {actionState.kind === "probing"
            && "Проверяю ответ и состав top‑40…"}
          {actionState.kind === "refreshing"
            && "Обновляю рейтинг, составы и профили игроков…"}
          {(actionState.kind === "success"
            || actionState.kind === "error")
            && actionState.message}
        </div>
      )}

      {latestRun && latestRun.player_profile_failures.length > 0 && (
        <section className="profile-failures">
          <strong>
            Не обновлены профили: {latestRun.player_profile_failures.length}
          </strong>
          <div className="profile-failures__list">
            {latestRun.player_profile_failures.map((failure) => (
              <a href={`/players/${failure.id}`} key={failure.id}>
                <span>{failure.nickname}</span>
                <small>{failure.bo3_slug} · {failure.error}</small>
              </a>
            ))}
          </div>
        </section>
      )}

      {probe && (
        <section className="probe-panel">
          <div>
            <span>Проверка источника</span>
            <strong>
              {probe.teams_received}/40 команд
            </strong>
          </div>
          <p>
            Дата ответа:{" "}
            {formatDate(probe.ranking_date)}.
            Первое место:{" "}
            {probe.teams[0]?.name || "—"}.
          </p>
        </section>
      )}

      <section className="ranking">
        <div className="section-heading">
          <div>
            <p className="eyebrow">
              Активная выборка
            </p>
            <h2>Команды</h2>
          </div>
          <span>
            {teams.length
              ? `${teams.length} записей · ${teams.filter((team) => !team.is_analytics_active).length} не считаем`
              : "данных пока нет"}
          </span>
        </div>

        {loadState.kind === "loading" && (
          <div className="empty-state">
            Загружаю команды…
          </div>
        )}

        {loadState.kind === "error" && (
          <div className="empty-state empty-state--error">
            {loadState.message}
          </div>
        )}

        {loadState.kind === "ready"
          && teams.length === 0 && (
            <div className="empty-state">
              <strong>Top‑30 ещё не загружен</strong>
              <span>
                Сначала можно проверить источник,
                затем нажать «Обновить top‑30».
              </span>
            </div>
          )}

        {teams.length > 0 && (
          <div className="team-grid">
            {teams.map((team) => (
              <TeamCard team={team} key={team.bo3_id} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
