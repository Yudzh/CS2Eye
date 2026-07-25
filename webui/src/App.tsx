import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getLatestRun,
  getTeams,
  probeTopTeams,
  refreshTopTeams,
  getPlayer,
  refreshPlayer,
} from "./api";
import type {
  ProbeResult,
  RankingRun,
  Team,
  TeamParticipant,
  Player,
} from "./types";


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
        <article className="metric-card"><span>player_strength</span><strong>{player.player_strength ?? "—"}<small>/100</small></strong></article>
        <article className="metric-card"><span>Рейтинг BO3 · 6 месяцев</span><strong>{player.bo3_rating === null ? "—" : Number(player.bo3_rating).toFixed(2)}</strong></article>
        <article className="metric-card"><span>Последнее обновление</span><strong className="metric-date">{formatDate(player.stats_synced_at)}</strong></article>
      </section>
      <section className="strength-panel">
        <div className="section-heading"><div><p className="eyebrow">Расшифровка</p><h2>Что повлияло на силу</h2></div></div>
        {player.strength_breakdown ? player.strength_breakdown.factors.map((factor) => (
          <div className="factor" key={factor.metric}><span className={`factor__impact factor__impact--${factor.direction}`}>{factor.impact > 0 ? "+" : ""}{factor.impact}</span><div><strong>Рейтинг BO3.gg: {factor.value.toFixed(2)}</strong><p>{factor.explanation}</p></div></div>
        )) : <div className="empty-state">BO3.gg пока не предоставил рейтинг. Нажмите «Обновить».</div>}
        {player.strength_breakdown && <small className="formula">{player.strength_breakdown.formula}</small>}
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
  const playerMatch = window.location.pathname.match(/^\/players\/(\d+)\/?$/);
  if (playerMatch) return <PlayerPage id={Number(playerMatch[1])} />;
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
          "Top-30, составы и профили игроков обновлены. "
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
          <strong>{teams.length}</strong>
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
            && "Проверяю ответ и состав top‑30…"}
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
              {probe.teams_received}/30 команд
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
              ? `${teams.length} записей`
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
          <div className="team-list">
            <div className="team-row team-row--header">
              <span>Место</span>
              <span>Команда</span>
              <span>Актуальный состав</span>
              <span>Очки</span>
              <span>Изменение</span>
            </div>

            {teams.map((team) => (
              <article
                className="team-row"
                key={team.bo3_id}
              >
                <strong className="rank">
                  {team.current_rank}
                </strong>
                <div className="team-identity">
                  {team.logo_url ? (
                    <img
                      alt=""
                      src={team.logo_url}
                    />
                  ) : (
                    <span className="team-logo">
                      {team.name.slice(0, 2)}
                    </span>
                  )}
                  <div>
                    <strong>{team.name}</strong>
                    <span>
                      {team.country_code || "—"}
                      {" · "}
                      {team.bo3_slug}
                    </span>
                  </div>
                </div>
                <div className="roster">
                  {team.roster.length ? (
                    <>
                      <RosterGroup
                        label="Основной состав"
                        members={team.roster.filter(
                          (participant) =>
                            participant.participant_type === "player",
                        )}
                      />
                      <RosterGroup
                        label="Запасные"
                        members={team.roster.filter(
                          (participant) =>
                            participant.participant_type === "substitute",
                        )}
                      />
                      <RosterGroup
                        label="Тренеры"
                        members={team.roster.filter(
                          (participant) =>
                            participant.participant_type === "coach",
                        )}
                      />
                    </>
                  ) : (
                    <span className="roster__empty">
                      состав не синхронизирован
                    </span>
                  )}
                  <small className="roster__synced">
                    Синхронизация: {formatDate(
                      team.roster_synced_at,
                    )}
                  </small>
                </div>
                <strong className="points">
                  {formatPoints(
                    team.current_points,
                  )}
                </strong>
                <span
                  className={
                    team.rank_change
                      && team.rank_change !== 0
                      ? team.rank_change > 0
                        ? "change change--up"
                        : "change change--down"
                      : "change"
                  }
                >
                  {rankChangeLabel(
                    team.rank_change,
                  )}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
