import {
  type FormEvent,
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
  ErrorState,
  LoadingState,
} from "../components/AsyncState";

import {
  formatDate,
} from "../lib/format";

import type {
  LiquipediaTeamPreview,
  LiquipediaTeamRequest,
  LiquipediaTeamResponse,
  TeamRoleCode,
} from "../types";


type SelectedRole =
  TeamRoleCode | "";


interface PreviewSource {
  team_page: string;
  team_name: string | null;
}


export function AdminTeamsImportPage() {
  const [
    teamPage,
    setTeamPage,
  ] = useState("");

  const [
    teamName,
    setTeamName,
  ] = useState("");

  const [
    preview,
    setPreview,
  ] = useState<
    LiquipediaTeamPreview | null
  >(null);

  const [
    previewSource,
    setPreviewSource,
  ] = useState<
    PreviewSource | null
  >(null);

  const [
    rolesByNickname,
    setRolesByNickname,
  ] = useState<
    Record<string, SelectedRole>
  >({});

  const [
    savedResult,
    setSavedResult,
  ] = useState<
    LiquipediaTeamResponse | null
  >(null);

  const [
    previewLoading,
    setPreviewLoading,
  ] = useState(false);

  const [
    saveLoading,
    setSaveLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  const activePlayers = useMemo(
    () =>
      preview?.players.filter(
        (player) =>
          player.status === "active",
      ) || [],
    [preview],
  );


  const missingRolePlayers = useMemo(
    () =>
      activePlayers.filter(
        (player) =>
          !rolesByNickname[
            player.nickname
          ],
      ),
    [
      activePlayers,
      rolesByNickname,
    ],
  );


  const canSave = Boolean(
    preview
    && previewSource
    && preview.active_players_count === 5
    && missingRolePlayers.length === 0
    && !saveLoading,
  );


  async function loadPreview(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const normalizedTeamPage =
      teamPage.trim();

    if (!normalizedTeamPage) {
      setError(
        "Укажи страницу или URL Liquipedia.",
      );

      return;
    }

    const request: LiquipediaTeamRequest = {
      team_page: normalizedTeamPage,

      team_name:
        teamName.trim() || null,

      override_roster: false,
      role_assignments: [],
    };

    setPreviewLoading(true);
    setError(null);
    setSavedResult(null);

    try {
      const response =
        await teamsApi.importFromLiquipedia(
          request,
        );

      const initialRoles: Record<
        string,
        SelectedRole
      > = {};

      for (
        const player
        of response.preview.players
      ) {
        if (player.status === "coach") {
          initialRoles[
            player.nickname
          ] = "coach";

          continue;
        }

        const detectedOption =
          response.preview.role_options.find(
            (option) =>
              option.value === player.role
              && option.allowed_statuses
                .includes("active"),
          );

        initialRoles[
          player.nickname
        ] = detectedOption
          ? detectedOption.value
          : "";
      }

      setPreview(response.preview);
      setRolesByNickname(initialRoles);

      setPreviewSource({
        team_page: normalizedTeamPage,

        team_name:
          teamName.trim() || null,
      });
    } catch (loadError) {
      setPreview(null);
      setPreviewSource(null);
      setRolesByNickname({});

      setError(
        loadError instanceof Error
          ? loadError.message
          : "Неизвестная ошибка Liquipedia.",
      );
    } finally {
      setPreviewLoading(false);
    }
  }


  function updateRole(
    nickname: string,
    role: SelectedRole,
  ) {
    setRolesByNickname(
      (currentRoles) => ({
        ...currentRoles,
        [nickname]: role,
      }),
    );

    setSavedResult(null);
  }


  async function saveTeam() {
    if (
      !preview
      || !previewSource
    ) {
      return;
    }

    if (missingRolePlayers.length > 0) {
      setError(
        "Не выбрана роль для: "
        + missingRolePlayers
          .map(
            (player) =>
              player.nickname,
          )
          .join(", "),
      );

      return;
    }

    const roleAssignments =
      preview.players.map(
        (player) => {
          const selectedRole =
            player.status === "coach"
              ? "coach"
              : rolesByNickname[
                  player.nickname
                ];

          if (!selectedRole) {
            throw new Error(
              "Не выбрана роль для "
              + player.nickname,
            );
          }

          return {
            nickname: player.nickname,
            role: selectedRole,
          };
        },
      );

    setSaveLoading(true);
    setError(null);
    setSavedResult(null);

    try {
      const response =
        await teamsApi.importFromLiquipedia({
          team_page:
            previewSource.team_page,

          team_name:
            previewSource.team_name,

          override_roster: true,

          role_assignments:
            roleAssignments,
        });

      setSavedResult(response);
      setPreview(response.preview);
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Не удалось сохранить команду.",
      );
    } finally {
      setSaveLoading(false);
    }
  }


  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            Администрирование
          </p>

          <h1>
            Импорт команды из Liquipedia
          </h1>

          <p className="page-heading__description">
            Получи актуальный состав,
            назначь основные роли игрокам
            и только после проверки
            сохрани команду.
          </p>
        </div>
      </section>

      <section className="admin-security-note">
        Эта страница пока не защищена
        авторизацией. Она предназначена
        для локального административного
        использования.
      </section>

      <form
        className="panel import-form"
        onSubmit={
          (event) =>
            void loadPreview(event)
        }
      >
        <div className="import-form__grid">
          <label>
            <span>
              Страница или URL Liquipedia
            </span>

            <input
              onChange={
                (event) =>
                  setTeamPage(
                    event.target.value,
                  )
              }
              placeholder={
                "Team_Spirit или "
                + "https://liquipedia.net/"
                + "counterstrike/Team_Spirit"
              }
              required
              type="text"
              value={teamPage}
            />
          </label>

          <label>
            <span>
              Название команды
              <small>
                необязательно
              </small>
            </span>

            <input
              onChange={
                (event) =>
                  setTeamName(
                    event.target.value,
                  )
              }
              placeholder={
                "Оставь пустым — "
                + "возьмём из Liquipedia"
              }
              type="text"
              value={teamName}
            />
          </label>
        </div>

        <div className="import-form__actions">
          <button
            className="button"
            disabled={previewLoading}
            type="submit"
          >
            {
              previewLoading
                ? "Загружаем..."
                : "Получить состав"
            }
          </button>
        </div>
      </form>

      {previewLoading ? (
        <LoadingState
          message={
            "Получаем состав "
            + "из Liquipedia..."
          }
        />
      ) : null}

      {error ? (
        <ErrorState message={error} />
      ) : null}

      {preview ? (
        <>
          <section className="panel section-panel">
            <div className="panel__heading">
              <div>
                <span className="panel__label">
                  Предпросмотр
                </span>

                <h2>{preview.team_name}</h2>
              </div>

              <a
                className="button button--secondary"
                href={preview.liquipedia_url}
                rel="noreferrer"
                target="_blank"
              >
                Открыть Liquipedia
              </a>
            </div>

            <div className="import-summary">
              <article>
                <span>
                  Активных игроков
                </span>

                <strong>
                  {
                    preview
                      .active_players_count
                  }
                </strong>
              </article>

              <article>
                <span>
                  Всего записей
                </span>

                <strong>
                  {preview.total_players}
                </strong>
              </article>

              <article>
                <span>
                  Ролей не назначено
                </span>

                <strong>
                  {
                    missingRolePlayers
                      .length
                  }
                </strong>
              </article>
            </div>
            {preview.active_players_count !== 5 ? (
              <p className="save-import-panel__error">
                Активный состав должен содержать
                ровно 5 игроков. Сейчас найдено:{" "}
                {preview.active_players_count}.
              </p>
            ) : null}

            {
              preview.warnings.length > 0
                ? (
                  <ul className="warning-list">
                    {
                      preview.warnings.map(
                        (warning) => (
                          <li key={warning}>
                            {warning}
                          </li>
                        ),
                      )
                    }
                  </ul>
                )
                : null
            }

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Игрок</th>
                    <th>Статус</th>
                    <th>В составе с</th>
                    <th>Роль</th>
                    <th>Источник</th>
                  </tr>
                </thead>

                <tbody>
                  {preview.players.map(
                    (player) => {
                      const availableOptions =
                        preview.role_options.filter(
                          (option) =>
                            option
                              .allowed_statuses
                              .includes(
                                player.status,
                              ),
                        );

                      return (
                        <tr
                          key={
                            `${player.status}:`
                            + player.nickname
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
                                || "Дополнительные "
                                + "данные отсутствуют"
                              }
                            </small>
                          </td>

                          <td>
                            {
                              player.status
                              === "coach"
                                ? "Тренер"
                                : "Основной состав"
                            }
                          </td>

                          <td>
                            {
                              formatDate(
                                player.joined_at,
                              )
                            }
                          </td>

                          <td>
                            <select
                              className={
                                `role-select${
                                  !rolesByNickname[
                                    player.nickname
                                  ]
                                    ? " role-select--invalid"
                                    : ""
                                }`
                              }
                              disabled={
                                player.status
                                === "coach"
                              }
                              onChange={(event) => {
                                  updateRole(
                                    player.nickname,
                                    event.target.value as SelectedRole,
                                  );
                                }}
                              value={
                                rolesByNickname[
                                  player.nickname
                                ] || ""
                              }
                            >
                              {
                                player.status
                                !== "coach"
                                  ? (
                                    <option value="">
                                      Выберите роль
                                    </option>
                                  )
                                  : null
                              }

                              {
                                availableOptions.map(
                                  (option) => (
                                    <option
                                      key={
                                        option.value
                                      }
                                      value={
                                        option.value
                                      }
                                    >
                                      {option.label}
                                    </option>
                                  ),
                                )
                              }
                            </select>
                          </td>

                          <td>
                            <a
                              className="table-link"
                              href={
                                player
                                  .liquipedia_url
                                || player.source_url
                              }
                              rel="noreferrer"
                              target="_blank"
                            >
                              Liquipedia
                            </a>
                          </td>
                        </tr>
                      );
                    },
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel save-import-panel">
            <div>
              <h2>
                Сохранение состава
              </h2>

              <p>
                Текущий активный состав
                команды в базе будет заменён
                составом из Liquipedia.
                Сохранённые рейтинги игроков
                не стираются, если Liquipedia
                не передала новые значения.
              </p>

              {
                missingRolePlayers.length > 0
                  ? (
                    <p className="save-import-panel__error">
                      Не выбрана роль для:{" "}
                      {
                        missingRolePlayers
                          .map(
                            (player) =>
                              player.nickname,
                          )
                          .join(", ")
                      }
                    </p>
                  )
                  : (
                    <p className="save-import-panel__ready">
                      Все обязательные роли
                      назначены.
                    </p>
                  )
              }
            </div>

            <button
              className="button"
              disabled={!canSave}
              onClick={
                () => void saveTeam()
              }
              type="button"
            >
              {
                saveLoading
                  ? "Сохраняем..."
                  : "Сохранить команду"
              }
            </button>
          </section>
        </>
      ) : null}

      {savedResult?.saved
      && savedResult.team ? (
        <section className="import-success">
          <div>
            <strong>
              Команда успешно сохранена
            </strong>

            <p>
              Состав и выбранные роли
              записаны в базу.
            </p>
          </div>

          <Link
            className="button"
            to={
              `/teams/${
                savedResult.team.id
              }`
            }
          >
            Открыть команду
          </Link>
        </section>
      ) : null}
    </>
  );
}