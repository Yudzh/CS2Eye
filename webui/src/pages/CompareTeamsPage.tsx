import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  TeamStrengthExplanation,
} from "../components/TeamStrengthExplanation";

import {
  useSearchParams,
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
  confidenceLabel,
  formatDate,
  formatNumber,
  formatPercent,
  mapTierLabel,
  roleLabel,
} from "../lib/format";

import type {
  TeamComparisonDashboard,
  TeamSummary,
} from "../types";


export function CompareTeamsPage() {
  const [
    searchParams,
  ] = useSearchParams();

  const [
    teams,
    setTeams,
  ] = useState<TeamSummary[]>([]);

  const [
    teamAId,
    setTeamAId,
  ] = useState(
    searchParams.get("team_a") || "",
  );

  const [
    teamBId,
    setTeamBId,
  ] = useState("");

  const [
    comparison,
    setComparison,
  ] = useState<
    TeamComparisonDashboard | null
  >(null);

  const [
    teamsLoading,
    setTeamsLoading,
  ] = useState(true);

  const [
    comparisonLoading,
    setComparisonLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  const loadTeams = useCallback(
    async () => {
      setTeamsLoading(true);
      setError(null);

      try {
        const payload =
          await teamsApi.list();

        setTeams(payload.items);

        setTeamAId(
          (current) =>
            current
            || payload.items[0]?.id
            || "",
        );

        setTeamBId(
          (current) => {
            if (current) {
              return current;
            }

            const firstTeamId =
              searchParams.get("team_a")
              || payload.items[0]?.id;

            return (
              payload.items.find(
                (team) =>
                  team.id !== firstTeamId,
              )?.id
              || ""
            );
          },
        );
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Неизвестная ошибка загрузки команд.",
        );
      } finally {
        setTeamsLoading(false);
      }
    },
    [searchParams],
  );


  useEffect(() => {
    void loadTeams();
  }, [loadTeams]);


  const canCompare = Boolean(
    teamAId
    && teamBId
    && teamAId !== teamBId,
  );


  const selectedTeamNames = useMemo(
    () => ({
      teamA:
        teams.find(
          (team) => team.id === teamAId,
        )?.name
        || "Команда A",

      teamB:
        teams.find(
          (team) => team.id === teamBId,
        )?.name
        || "Команда B",
    }),
    [
      teamAId,
      teamBId,
      teams,
    ],
  );


  async function submitComparison(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!canCompare) {
      setError(
        "Выберите две разные команды.",
      );

      return;
    }

    setComparisonLoading(true);
    setComparison(null);
    setError(null);

    try {
      setComparison(
        await teamsApi.compare(
          teamAId,
          teamBId,
        ),
      );
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Неизвестная ошибка сравнения команд.",
      );
    } finally {
      setComparisonLoading(false);
    }
  }


  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            Предматчевая аналитика
          </p>

          <h1>Сравнение команд</h1>

          <p className="page-heading__description">
            Сила составов, карта-пул и
            последние десять очных карт.
          </p>
        </div>
      </section>

      <form
        className="comparison-form"
        onSubmit={
          (event) =>
            void submitComparison(event)
        }
      >
        <label>
          <span>Команда A</span>

          <select
            onChange={
              (event) =>
                setTeamAId(
                  event.target.value,
                )
            }
            value={teamAId}
          >
            <option value="">
              Выберите команду
            </option>

            {teams.map(
              (team) => (
                <option
                  key={team.id}
                  value={team.id}
                >
                  {team.name}
                </option>
              ),
            )}
          </select>
        </label>

        <span className="versus">
          VS
        </span>

        <label>
          <span>Команда B</span>

          <select
            onChange={
              (event) =>
                setTeamBId(
                  event.target.value,
                )
            }
            value={teamBId}
          >
            <option value="">
              Выберите команду
            </option>

            {teams.map(
              (team) => (
                <option
                  key={team.id}
                  value={team.id}
                >
                  {team.name}
                </option>
              ),
            )}
          </select>
        </label>

        <button
          className="button"
          disabled={
            !canCompare
            || comparisonLoading
          }
          type="submit"
        >
          {
            comparisonLoading
              ? "Считаем..."
              : "Сравнить"
          }
        </button>
      </form>

      {teamsLoading ? (
        <LoadingState
          message="Загружаем список команд..."
        />
      ) : null}

      {!teamsLoading && error ? (
        <ErrorState message={error} />
      ) : null}

      {comparisonLoading ? (
        <LoadingState
          message="Собираем сравнение команд..."
        />
      ) : null}

      {!teamsLoading
      && !comparisonLoading
      && !comparison
      && !error ? (
        <EmptyState
          message={
            `Выберите ${selectedTeamNames.teamA}`
            + ` и ${selectedTeamNames.teamB}, `
            + "затем нажмите «Сравнить»."
          }
        />
      ) : null}

      {comparison ? (
        <>
          <section className="versus-grid">
            <article className="versus-card">
              <RosterStateBadge
                state={
                  comparison.team_a
                    .roster_state
                }
              />

              <h2>
                {
                  comparison.team_a
                    .team_name
                }
              </h2>

              <strong className="versus-card__percent">
                {
                  formatPercent(
                    comparison.team_a
                      .relative_strength_percent,
                  )
                }
              </strong>

              <p>
                Относительная сила
                в текущей паре
              </p>

              <dl>
                <div>
                  <dt>Сила состава</dt>

                  <dd>
                    {
                      formatNumber(
                        comparison.team_a
                          .team_strength_score,
                      )
                    }
                  </dd>
                </div>


                <div className="comparison-strength-details">
                  <TeamStrengthExplanation
                    compact
                    strength={comparison.team_a}
                  />

                  <TeamStrengthExplanation
                    compact
                    strength={comparison.team_b}
                  />
                </div>

                <div>
                  <dt>
                    Активных игроков
                  </dt>

                  <dd>
                    {
                      comparison.team_a
                        .active_players_count
                    }
                  </dd>
                </div>
              </dl>
            </article>

            <div className="versus-divider">
              <span>Преимущество</span>

              <strong>
                {
                  comparison
                    .strength_advantage_team_name
                  || "Равные силы"
                }
              </strong>

              <small>
                {
                  formatNumber(
                    comparison
                      .strength_advantage_diff,
                  )
                }{" "}
                пункта
              </small>
            </div>

            <article className="versus-card">
              <RosterStateBadge
                state={
                  comparison.team_b
                    .roster_state
                }
              />

              <h2>
                {
                  comparison.team_b
                    .team_name
                }
              </h2>

              <strong className="versus-card__percent">
                {
                  formatPercent(
                    comparison.team_b
                      .relative_strength_percent,
                  )
                }
              </strong>

              <p>
                Относительная сила
                в текущей паре
              </p>

              <dl>
                <div>
                  <dt>Сила состава</dt>

                  <dd>
                    {
                      formatNumber(
                        comparison.team_b
                          .team_strength_score,
                      )
                    }
                  </dd>
                </div>

                <div>
                  <dt>
                    Активных игроков
                  </dt>

                  <dd>
                    {
                      comparison.team_b
                        .active_players_count
                    }
                  </dd>
                </div>
              </dl>
            </article>
          </section>

          {
            comparison.summary_notes.length > 0
              ? (
                <section className="panel section-panel">
                  <div className="panel__heading">
                    <h2>Короткий вывод</h2>
                  </div>

                  <ul className="notice-list">
                    {
                      comparison.summary_notes.map(
                        (note) => (
                          <li key={note}>
                            {note}
                          </li>
                        ),
                      )
                    }
                  </ul>
                </section>
              )
              : null
          }

          <section className="panel section-panel">
            <div className="panel__heading">
              <div>
                <span className="panel__label">
                  Map matchup
                </span>

                <h2>
                  Сравнение по картам
                </h2>
              </div>
            </div>

            {
              comparison
                .map_comparisons.length === 0
                ? (
                  <p className="panel__note">
                    Нет общих данных по картам.
                  </p>
                )
                : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Карта</th>

                          <th>
                            {
                              comparison.team_a
                                .team_name
                            }
                          </th>

                          <th>
                            {
                              comparison.team_b
                                .team_name
                            }
                          </th>

                          <th>
                            Преимущество
                          </th>

                          <th>
                            Доверие
                          </th>
                        </tr>
                      </thead>

                      <tbody>
                        {
                          comparison
                            .map_comparisons
                            .map(
                              (map) => (
                                <tr
                                  key={
                                    map.map_name
                                    || "unknown-map"
                                  }
                                >
                                  <td>
                                    <strong>
                                      {
                                        map.map_name
                                        || "Неизвестная карта"
                                      }
                                    </strong>
                                  </td>

                                  <td>
                                    <strong>
                                      {
                                        formatPercent(
                                          map
                                            .team_a_relative_strength_percent,
                                        )
                                      }
                                    </strong>

                                    <small>
                                      сила{" "}
                                      {
                                        formatNumber(
                                          map.team_a
                                            .map_strength_score,
                                        )
                                      }
                                      {" · "}
                                      {
                                        map.team_a
                                          .total_matches
                                      }{" "}
                                      игр
                                      {" · "}
                                      {
                                        mapTierLabel(
                                          map.team_a
                                            .map_tier,
                                        )
                                      }
                                    </small>
                                  </td>

                                  <td>
                                    <strong>
                                      {
                                        formatPercent(
                                          map
                                            .team_b_relative_strength_percent,
                                        )
                                      }
                                    </strong>

                                    <small>
                                      сила{" "}
                                      {
                                        formatNumber(
                                          map.team_b
                                            .map_strength_score,
                                        )
                                      }
                                      {" · "}
                                      {
                                        map.team_b
                                          .total_matches
                                      }{" "}
                                      игр
                                      {" · "}
                                      {
                                        mapTierLabel(
                                          map.team_b
                                            .map_tier,
                                        )
                                      }
                                    </small>
                                  </td>

                                  <td>
                                    {
                                      map
                                        .advantage_team_name
                                      || "Нет явного преимущества"
                                    }
                                  </td>

                                  <td>
                                    {
                                      confidenceLabel(
                                        map
                                          .matchup_confidence_level,
                                      )
                                    }
                                  </td>
                                </tr>
                              ),
                            )
                        }
                      </tbody>
                    </table>
                  </div>
                )
            }
          </section>

          <section className="panel section-panel">
            <div className="panel__heading">
              <div>
                <span className="panel__label">
                  Head-to-head
                </span>

                <h2>
                  Последние очные карты
                </h2>
              </div>

              <span className="table-count">
                {
                  comparison
                    .recent_head_to_head_maps
                    .length
                }
                /10
              </span>
            </div>

            {
              comparison
                .recent_head_to_head_maps
                .length === 0
                ? (
                  <p className="panel__note">
                    Очные карты в базе
                    не найдены.
                  </p>
                )
                : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Дата</th>
                          <th>Турнир</th>
                          <th>Карта</th>
                          <th>Счёт</th>
                          <th>Победитель</th>
                        </tr>
                      </thead>

                      <tbody>
                        {
                          comparison
                            .recent_head_to_head_maps
                            .map(
                              (meeting) => (
                                <tr
                                  key={
                                    meeting.parse_run_id
                                  }
                                >
                                  <td>
                                    {
                                      formatDate(
                                        meeting
                                          .match_date,
                                      )
                                    }
                                  </td>

                                  <td>
                                    {
                                      meeting
                                        .tournament_name
                                      || "—"
                                    }
                                  </td>

                                  <td>
                                    <strong>
                                      {
                                        meeting.map_name
                                        || "—"
                                      }
                                    </strong>
                                  </td>

                                  <td>
                                    <strong>
                                      {
                                        meeting
                                          .team_a_rounds
                                      }
                                      :
                                      {
                                        meeting
                                          .team_b_rounds
                                      }
                                    </strong>

                                    <small>
                                      {
                                        meeting
                                          .team_a_name
                                      }
                                      {" — "}
                                      {
                                        meeting
                                          .team_b_name
                                      }
                                    </small>
                                  </td>

                                  <td>
                                    {
                                      meeting
                                        .winner_team_name
                                      || "Ничья / нет данных"
                                    }
                                  </td>
                                </tr>
                              ),
                            )
                        }
                      </tbody>
                    </table>
                  </div>
                )
            }
          </section>

          <section className="panel section-panel">
            <div className="panel__heading">
              <div>
                <span className="panel__label">
                  Role matchup
                </span>

                <h2>
                  Сравнение игроков
                  по ролям
                </h2>
              </div>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Роль</th>

                    <th>
                      {
                        comparison.team_a
                          .team_name
                      }
                    </th>

                    <th>
                      {
                        comparison.team_b
                          .team_name
                      }
                    </th>

                    <th>
                      Преимущество
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {
                    comparison
                      .role_comparisons
                      .map(
                        (role) => (
                          <tr key={role.role}>
                            <td>
                              <strong>
                                {
                                  roleLabel(
                                    role.role,
                                  )
                                }
                              </strong>
                            </td>

                            <td>
                              <strong>
                                {
                                  formatNumber(
                                    role
                                      .team_a_score,
                                  )
                                }
                              </strong>

                              <small>
                                {
                                  role
                                    .team_a_players
                                    .join(", ")
                                  || "Игрок не указан"
                                }
                              </small>
                            </td>

                            <td>
                              <strong>
                                {
                                  formatNumber(
                                    role
                                      .team_b_score,
                                  )
                                }
                              </strong>

                              <small>
                                {
                                  role
                                    .team_b_players
                                    .join(", ")
                                  || "Игрок не указан"
                                }
                              </small>
                            </td>

                            <td>
                              {
                                role
                                  .advantage_team_name
                                || "Равные показатели"
                              }
                            </td>
                          </tr>
                        ),
                      )
                  }
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}