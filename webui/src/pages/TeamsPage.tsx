import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Link,
} from "react-router-dom";

import {
  teamsApi,
} from "../api/teams";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/AsyncState";

import {
  RosterStateBadge,
} from "../components/RosterStateBadge";

import {
  StrengthBar,
} from "../components/StrengthBar";

import {
  formatNumber,
} from "../lib/format";

import type {
  TeamSummary,
} from "../types";


export function TeamsPage() {
  const [
    teams,
    setTeams,
  ] = useState<TeamSummary[]>([]);

  const [
    query,
    setQuery,
  ] = useState("");

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  const loadTeams = useCallback(
    async () => {
      setLoading(true);
      setError(null);

      try {
        const payload =
          await teamsApi.list();

        setTeams(payload.items);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Неизвестная ошибка загрузки команд.",
        );
      } finally {
        setLoading(false);
      }
    },
    [],
  );


  useEffect(() => {
    void loadTeams();
  }, [loadTeams]);


  const visibleTeams = useMemo(
    () => {
      const normalizedQuery =
        query
          .trim()
          .toLocaleLowerCase("ru");

      if (!normalizedQuery) {
        return teams;
      }

      return teams.filter(
        (team) =>
          [
            team.name,
            team.country,
            team.region,
          ]
            .filter(Boolean)
            .some(
              (value) =>
                value!
                  .toLocaleLowerCase("ru")
                  .includes(normalizedQuery),
            ),
      );
    },
    [
      query,
      teams,
    ],
  );


  const averageStrength = useMemo(
    () => {
      if (teams.length === 0) {
        return 0;
      }

      return (
        teams.reduce(
          (sum, team) =>
            sum + team.team_strength_score,
          0,
        )
        / teams.length
      );
    },
    [teams],
  );


  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            База команд
          </p>

          <h1>Команды</h1>

          <p className="page-heading__description">
            Текущие составы, стабильность
            ростера и рассчитанная сила команд.
          </p>
        </div>

        <div className="page-actions">
          <Link
            className="button button--secondary"
            to="/admin/teams/import"
          >
            Добавить или обновить команду
          </Link>

          <Link
            className="button"
            to="/compare"
          >
            Сравнить команды
          </Link>
        </div>
      </section>

      <section
        className="summary-grid"
        aria-label="Сводка по командам"
      >
        <article className="metric-card">
          <span>Команд в базе</span>

          <strong>
            {teams.length}
          </strong>
        </article>

        <article className="metric-card">
          <span>
            Стабильных составов
          </span>

          <strong>
            {
              teams.filter(
                (team) =>
                  team.roster_state.code
                  === "stable",
              ).length
            }
          </strong>
        </article>

        <article className="metric-card">
          <span>Средняя сила</span>

          <strong>
            {formatNumber(averageStrength)}
          </strong>
        </article>
      </section>

      <section className="toolbar">
        <label className="search-field">
          <span>Поиск команды</span>

          <input
            onChange={(event) =>
              setQuery(event.target.value)
            }
            placeholder="Например, Team Spirit"
            type="search"
            value={query}
          />
        </label>

        <button
          className="button button--secondary"
          onClick={() => void loadTeams()}
          type="button"
        >
          Обновить
        </button>
      </section>

      {loading ? (
        <LoadingState
          message="Загружаем команды..."
        />
      ) : null}

      {!loading && error ? (
        <ErrorState
          message={error}
          onRetry={() => void loadTeams()}
        />
      ) : null}

      {!loading
      && !error
      && visibleTeams.length === 0 ? (
        <EmptyState
          message={
            query
              ? "По этому запросу команды не найдены."
              : "В базе пока нет команд."
          }
        />
      ) : null}

      {!loading
      && !error
      && visibleTeams.length > 0 ? (
        <section className="team-grid">
          {visibleTeams.map(
            (team) => (
              <article
                className="team-card"
                key={team.id}
              >
                <div className="team-card__header">
                  <div>
                    <h2>{team.name}</h2>

                    <p>
                      {
                        [
                          team.country,
                          team.region,
                        ]
                          .filter(Boolean)
                          .join(" · ")
                        || "Регион не указан"
                      }
                    </p>
                  </div>

                  <span className="player-count">
                    {team.active_players_count}/5
                  </span>
                </div>

                <RosterStateBadge
                  state={team.roster_state}
                />

                <p className="team-card__note">
                  {team.roster_state.note}
                </p>

                <StrengthBar
                  compact
                  value={
                    team.team_strength_score
                  }
                />

                <Link
                  className="button button--full"
                  to={`/teams/${team.id}`}
                >
                  Открыть команду
                </Link>
              </article>
            ),
          )}
        </section>
      ) : null}
    </>
  );
}