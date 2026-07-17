import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  TeamStrengthExplanation,
} from "../components/TeamStrengthExplanation";

import {
  Link,
  useParams,
} from "react-router-dom";

import {
  teamsApi,
} from "../api/teams";

import {
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
  confidenceLabel,
  formatDate,
  formatNumber,
  formatPercent,
  mapTierLabel,
  roleLabel,
  rosterMemberStatusLabel,
} from "../lib/format";

import type {
  TeamDashboard,
} from "../types";


export function TeamDetailsPage() {
  const {
    teamId,
  } = useParams();

  const [
    team,
    setTeam,
  ] = useState<TeamDashboard | null>(null);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  const loadTeam = useCallback(
    async () => {
      if (!teamId) {
        setError(
          "Не передан идентификатор команды.",
        );

        setLoading(false);

        return;
      }

      setLoading(true);
      setError(null);

      try {
        setTeam(
          await teamsApi.getDashboard(teamId),
        );
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Неизвестная ошибка загрузки команды.",
        );
      } finally {
        setLoading(false);
      }
    },
    [teamId],
  );


  useEffect(() => {
    void loadTeam();
  }, [loadTeam]);


  if (loading) {
    return (
      <LoadingState
        message="Загружаем команду..."
      />
    );
  }


  if (error || !team) {
    return (
      <ErrorState
        message={
          error || "Команда не найдена."
        }
        onRetry={() => void loadTeam()}
      />
    );
  }


  return (
    <>
      <Link
        className="back-link"
        to="/teams"
      >
        ← Вернуться к командам
      </Link>

      <section className="page-heading page-heading--team">
        <div>
          <p className="eyebrow">
            Карточка команды
          </p>

          <h1>{team.name}</h1>

          <p className="page-heading__description">
            {
              [
                team.country,
                team.region,
              ]
                .filter(Boolean)
                .join(" · ")
              || "Страна и регион не указаны"
            }
          </p>
        </div>

        <Link
          className="button"
          to={`/compare?team_a=${team.id}`}
        >
          Сравнить с другой командой
        </Link>
      </section>

      <section className="dashboard-grid">
        <article className="panel panel--strength">
          <div className="panel__heading">
            <div>
              <span className="panel__label">
                Текущий состав
              </span>

              <h2>Сила команды</h2>
            </div>

            <RosterStateBadge
              state={team.roster_state}
            />
          </div>

          <StrengthBar
            value={
              team.strength.team_strength_score
            }
          />

          <TeamStrengthExplanation
              strength={team.strength}
            />

          <p className="panel__note">
            {team.roster_state.note}
          </p>
        </article>

        <article className="metric-card">
          <span>
            Активных игроков
          </span>

          <strong>
            {
              team.strength
                .active_players_count
            }
          </strong>

          <small>
            Для полного состава требуется 5
          </small>
        </article>

        <article className="metric-card">
          <span>
            Средняя сила игроков
          </span>

          <strong>
            {
              formatNumber(
                team.strength.base_player_score,
              )
            }
          </strong>

          <small>
            До бонусов и штрафов состава
          </small>
        </article>

        <article className="metric-card">
          <span>
            Корректировка состава
          </span>

          <strong>
            +
            {
              formatNumber(
                team.strength.roster_bonus,
              )
            }
            {" / -"}
            {
              formatNumber(
                team.strength.roster_penalty,
              )
            }
          </strong>

          <small>
            Бонус стабильности и штрафы
          </small>
        </article>
      </section>

      <section className="panel section-panel">
        <div className="panel__heading">
          <div>
            <span className="panel__label">
              Ростер
            </span>

            <h2>Состав команды</h2>
          </div>

          <span className="table-count">
            {team.roster.length} записей
          </span>
        </div>

        {team.strength.notes.length > 0 ? (
          <ul className="notice-list">
            {team.strength.notes.map(
              (note) => (
                <li key={note}>
                  {note}
                </li>
              ),
            )}
          </ul>
        ) : null}

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Игрок</th>
                <th>Статус</th>
                <th>Роль</th>
                <th>В составе с</th>
                <th>Rating</th>
                <th>Сила</th>
              </tr>
            </thead>

            <tbody>
              {team.roster.map(
                (player) => (
                  <tr
                    key={
                      player.roster_member_id
                    }
                  >
                    <td>
                      <strong>
                        {player.nickname}
                      </strong>

                      <small>
                        {
                          player.real_name
                          || player.country
                          || "Данные не указаны"
                        }
                      </small>
                    </td>

                    <td>
                      {
                        rosterMemberStatusLabel(
                          player.status,
                        )
                      }
                    </td>

                    <td>
                      {roleLabel(player.role)}
                    </td>

                    <td>
                      {
                        formatDate(
                          player.joined_at,
                        )
                      }
                    </td>

                    <td>
                      {
                        formatNumber(
                          player.current_rating,
                          2,
                        )
                      }
                    </td>

                    <td>
                      <strong>
                        {
                          formatNumber(
                            player
                              .player_strength_score,
                          )
                        }
                      </strong>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel section-panel">
        <div className="panel__heading">
          <div>
            <span className="panel__label">
              Map pool
            </span>

            <h2>Карты команды</h2>
          </div>

          <span className="table-count">
            {team.maps.length} карт
          </span>
        </div>

        {team.maps.length === 0 ? (
          <p className="panel__note">
            Для этой команды пока нет
            распарсенных карт.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Карта</th>
                  <th>Матчи</th>
                  <th>Победы</th>
                  <th>CT</th>
                  <th>T</th>
                  <th>Сила</th>
                  <th>Доверие</th>
                  <th>Статус</th>
                  <th>Последняя игра</th>
                </tr>
              </thead>

              <tbody>
                {team.maps.map(
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
                        {map.total_matches}
                      </td>

                      <td>
                        {
                          formatPercent(
                            map.win_rate,
                          )
                        }
                      </td>

                      <td>
                        {
                          formatPercent(
                            map.ct_win_rate,
                          )
                        }
                      </td>

                      <td>
                        {
                          formatPercent(
                            map.t_win_rate,
                          )
                        }
                      </td>

                      <td>
                        <strong>
                          {
                            formatNumber(
                              map.map_strength_score,
                            )
                          }
                        </strong>
                      </td>

                      <td>
                        {
                          confidenceLabel(
                            map.confidence_level,
                          )
                        }

                        <small>
                          {
                            formatNumber(
                              map.confidence_score,
                            )
                          }
                        </small>
                      </td>

                      <td>
                        {
                          mapTierLabel(
                            map.map_tier,
                          )
                        }
                      </td>

                      <td>
                        {
                          formatDate(
                            map.last_played_date,
                          )
                        }
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}