import {
  ACTIVE_ROSTER_SIZE,
  isActiveRosterStatus,
  isCoachRosterStatus,
} from "../lib/roster";

import {
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
  ErrorState,
  LoadingState,
} from "../components/AsyncState";

import type {
  AdminTeam,
  ManualRosterPlayerUpdate,
  RosterMemberStatus,
  TeamRoleCode,
  TeamRoleOption,
} from "../types";


interface EditableRosterPlayer {
  key: string;

  originalNickname: string | null;
  nickname: string;

  status: RosterMemberStatus;
  role: TeamRoleCode | "";

  realName: string;
  country: string;
  joinedAt: string;

  currentRating: string;
  strengthScore: string;

  notes: string;
  deleted: boolean;
}

function parseRosterStatus(
  value: string,
): RosterMemberStatus {
  if (
    value === "active"
    || value === "coach"
  ) {
    return value;
  }

  throw new Error(
    `Неизвестный статус состава: ${value}`,
  );
}


function parseTeamRole(
  value: string | null,
): TeamRoleCode | "" {
  switch (value) {
    case "":
    case null:
      return "";

    case "igl":
    case "awper":
    case "rifler":
    case "entry_frag":
    case "lurk":
    case "anchor_support":
    case "coach":
      return value;

    default:
      return "";
  }
}


function rosterToRows(
  team: AdminTeam,
): EditableRosterPlayer[] {
  return team.roster.map(
    (member) => ({
      key: member.roster_member_id,

      originalNickname:
        member.nickname,

      nickname:
        member.nickname,

      status:
        member.status === "coach"
          ? "coach"
          : "active",

      role:
        parseTeamRole(member.role),

      realName:
        member.real_name || "",

      country:
        member.country || "",

      joinedAt:
        member.joined_at || "",

      currentRating:
        member.current_rating
          ?.toString()
        || "",

      strengthScore:
        member.player_strength_score
          .toString(),

      notes:
        member.notes || "",

      deleted: false,
    }),
  );
}


function nullableText(
  value: string,
): string | null {
  const normalized = value.trim();

  return normalized || null;
}


function nullableNumber(
  value: string,
): number | null {
  const normalized = value.trim();

  if (!normalized) {
    return null;
  }

  const parsed = Number(normalized);

  if (!Number.isFinite(parsed)) {
    return null;
  }

  return parsed;
}


export function AdminTeamsPage() {
  const [
    teams,
    setTeams,
  ] = useState<AdminTeam[]>([]);

  const [
    roleOptions,
    setRoleOptions,
  ] = useState<TeamRoleOption[]>([]);

  const [
    selectedTeamName,
    setSelectedTeamName,
  ] = useState("");

  const [
    rows,
    setRows,
  ] = useState<
    EditableRosterPlayer[]
  >([]);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    saving,
    setSaving,
  ] = useState(false);

  const [
    deletingTeam,
    setDeletingTeam,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);

  const [
    successMessage,
    setSuccessMessage,
  ] = useState<string | null>(null);


  const selectedTeam = useMemo(
    () =>
      teams.find(
        (team) =>
          team.name
          === selectedTeamName,
      ) || null,
    [
      teams,
      selectedTeamName,
    ],
  );


  const visibleRows = useMemo(
    () =>
      rows.filter(
        (row) => !row.deleted,
      ),
    [rows],
  );


  const activeCount = useMemo(
  () =>
    visibleRows.filter(
      (row) =>
        isActiveRosterStatus(
          row.status,
        ),
    ).length,
  [visibleRows],
);


const coachCount = useMemo(
  () =>
    visibleRows.filter(
      (row) =>
        isCoachRosterStatus(
          row.status,
        ),
    ).length,
  [visibleRows],
);


  const rolesComplete = useMemo(
    () =>
      visibleRows.every(
        (row) =>
          row.nickname.trim()
          && row.role,
      ),
    [visibleRows],
  );


  const canSave = Boolean(
    selectedTeam
    && activeCount === ACTIVE_ROSTER_SIZE
    && coachCount <= 1
    && rolesComplete
    && !saving,
  );


  useEffect(
    () => {
      void loadTeams();
    },
    [],
  );


  useEffect(
    () => {
      if (!selectedTeam) {
        setRows([]);
        return;
      }

      setRows(
        rosterToRows(selectedTeam),
      );

      setError(null);
      setSuccessMessage(null);
    },
    [selectedTeam],
  );


  async function loadTeams() {
    setLoading(true);
    setError(null);

    try {
      const [
        teamsResponse,
        rolesResponse,
      ] = await Promise.all([
        teamsApi.listAdmin(),
        teamsApi.getRoleOptions(),
      ]);

      setTeams(
        teamsResponse.items,
      );

      setRoleOptions(
        rolesResponse,
      );

      setSelectedTeamName(
        (currentName) => {
          if (
            teamsResponse.items.some(
              (team) =>
                team.name
                === currentName,
            )
          ) {
            return currentName;
          }

          return (
            teamsResponse.items[0]
              ?.name
            || ""
          );
        },
      );
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Не удалось загрузить команды.",
      );
    } finally {
      setLoading(false);
    }
  }


  function updateRow(
    key: string,
    patch: Partial<
      EditableRosterPlayer
    >,
  ) {
    setRows(
      (currentRows) =>
        currentRows.map(
          (row) =>
            row.key === key
              ? {
                  ...row,
                  ...patch,
                }
              : row,
        ),
    );

    setSuccessMessage(null);
  }


  function changeStatus(
    row: EditableRosterPlayer,
    status: RosterMemberStatus,
  ) {
    if (status === "coach") {
      updateRow(
        row.key,
        {
          status: "coach",
          role: "coach",
        },
      );

      return;
    }

    updateRow(
      row.key,
      {
        status: "active",

        role:
          row.role === "coach"
            ? ""
            : row.role,
      },
    );
  }


  function changeRole(
    row: EditableRosterPlayer,
    role: TeamRoleCode | "",
  ) {
    updateRow(
      row.key,
      {
        role,

        status:
          role === "coach"
            ? "coach"
            : "active",
      },
    );
  }


  function addPlayer() {
    const key = [
      "new",
      Date.now(),
      Math.random(),
    ].join("-");

    setRows(
      (currentRows) => [
        ...currentRows,
        {
          key,

          originalNickname: null,
          nickname: "",

          status: "active",
          role: "rifler",

          realName: "",
          country: "",
          joinedAt: "",

          currentRating: "",
          strengthScore: "50",

          notes: "",
          deleted: false,
        },
      ],
    );

    setSuccessMessage(null);
  }


  function markPlayerDeleted(
    row: EditableRosterPlayer,
  ) {
    if (row.originalNickname === null) {
      setRows(
        (currentRows) =>
          currentRows.filter(
            (item) =>
              item.key !== row.key,
          ),
      );

      return;
    }

    updateRow(
      row.key,
      {
        deleted: true,
      },
    );
  }


  function restorePlayer(
    row: EditableRosterPlayer,
  ) {
    updateRow(
      row.key,
      {
        deleted: false,
      },
    );
  }


  async function saveRoster() {
    if (!selectedTeam) {
      return;
    }

    if (activeCount !== 5) {
      setError(
        "В основном составе должно быть "
        + "ровно 5 игроков.",
      );

      return;
    }

    if (coachCount > 1) {
      setError(
        "У команды не может быть "
        + "больше одного тренера.",
      );

      return;
    }

    const activeNicknames =
      visibleRows.map(
        (row) =>
          row.nickname
            .trim()
            .toLowerCase()
          || row.nickname
            .trim()
            .toLowerCase(),
      );

    if (
      new Set(activeNicknames).size
      !== activeNicknames.length
    ) {
      setError(
        "В составе есть повторяющиеся "
        + "никнеймы.",
      );

      return;
    }

    const requestPlayers:
      ManualRosterPlayerUpdate[] = [];

    for (const row of rows) {
      if (row.deleted) {
        if (row.originalNickname) {
          requestPlayers.push({
            nickname:
              row.originalNickname,

            delete: 1,
            role: null,

            real_name: null,
            country: null,

            joined_at: null,
            left_at: null,

            liquipedia_url: null,
            hltv_id: null,

            current_rating: null,

            player_strength_score:
              null,

            notes: null,
          });
        }

        continue;
      }

      const nickname =
        row.nickname.trim();

      if (!nickname || !row.role) {
        setError(
          "У каждого игрока должны быть "
          + "никнейм и роль.",
        );

        return;
      }

      requestPlayers.push({
        nickname,
        delete: 0,
        role: row.role,

        real_name:
          nullableText(
            row.realName,
          ),

        country:
          nullableText(
            row.country,
          ),

        joined_at:
          nullableText(
            row.joinedAt,
          ),

        left_at: null,

        liquipedia_url: null,
        hltv_id: null,

        current_rating:
          nullableNumber(
            row.currentRating,
          ),

        player_strength_score:
          nullableNumber(
            row.strengthScore,
          ),

        notes:
          nullableText(
            row.notes,
          ),
      });

      if (
        row.originalNickname
        && row.originalNickname
          .toLowerCase()
        !== nickname.toLowerCase()
      ) {
        requestPlayers.push({
          nickname:
            row.originalNickname,

          delete: 1,
          role: null,

          real_name: null,
          country: null,

          joined_at: null,
          left_at: null,

          liquipedia_url: null,
          hltv_id: null,

          current_rating: null,

          player_strength_score:
            null,

          notes: null,
        });
      }
    }

    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const savedTeam =
        await teamsApi.updateRoster(
          selectedTeam.name,
          {
            players:
              requestPlayers,
          },
        );

      setTeams(
        (currentTeams) =>
          currentTeams.map(
            (team) =>
              team.id === savedTeam.id
                ? savedTeam
                : team,
          ),
      );

      setRows(
        rosterToRows(savedTeam),
      );

      setSuccessMessage(
        "Состав команды сохранён.",
      );
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Не удалось сохранить состав.",
      );
    } finally {
      setSaving(false);
    }
  }


  async function removeTeam() {
    if (!selectedTeam) {
      return;
    }

    const confirmed = window.confirm(
      `Удалить команду `
      + `"${selectedTeam.name}"? `
      + "Состав команды также будет удалён.",
    );

    if (!confirmed) {
      return;
    }

    setDeletingTeam(true);
    setError(null);
    setSuccessMessage(null);

    try {
      await teamsApi.deleteTeam(
        selectedTeam.name,
      );

      const remainingTeams =
        teams.filter(
          (team) =>
            team.id !== selectedTeam.id,
        );

      setTeams(remainingTeams);

      setSelectedTeamName(
        remainingTeams[0]?.name || "",
      );

      setSuccessMessage(
        "Команда удалена.",
      );
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Не удалось удалить команду.",
      );
    } finally {
      setDeletingTeam(false);
    }
  }


  if (loading) {
    return (
      <LoadingState
        message="Загружаем команды..."
      />
    );
  }


  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            Администрирование
          </p>

          <h1>
            Управление командами
          </h1>

          <p className="page-heading__description">
            Редактирование текущего
            состава, ролей и индивидуальных
            показателей игроков.
          </p>
        </div>

        <Link
          className="button"
          to="/admin/teams/import"
        >
          Добавить команду
        </Link>
      </section>

      <section className="admin-security-note">
        Страница пока не защищена
        авторизацией и предназначена
        для локального использования.
      </section>

      {error ? (
        <ErrorState message={error} />
      ) : null}

      {successMessage ? (
        <section className="import-success">
          <strong>
            {successMessage}
          </strong>
        </section>
      ) : null}

      {teams.length === 0 ? (
        <section className="panel empty-state">
          <h2>
            Команд пока нет
          </h2>

          <p>
            Сначала добавь команду
            через Liquipedia.
          </p>
        </section>
      ) : (
        <>
          <section className="panel admin-team-selector">
            <label>
              <span>
                Команда
              </span>

              <select
                onChange={
                  (event) =>
                    setSelectedTeamName(
                      event.target.value,
                    )
                }
                value={selectedTeamName}
              >
                {teams.map(
                  (team) => (
                    <option
                      key={team.id}
                      value={team.name}
                    >
                      {team.name}
                    </option>
                  ),
                )}
              </select>
            </label>

            {selectedTeam ? (
              <div className="admin-team-actions">
                <Link
                  className="button button--secondary"
                  to={
                    `/teams/${selectedTeam.id}`
                  }
                >
                  Открыть карточку
                </Link>

                <Link
                  className="button button--secondary"
                  to={
                    `/admin/teams/import?${new URLSearchParams({
                      teamPage:
                        selectedTeam
                          .liquipedia_url
                        || selectedTeam.name,

                      teamName:
                        selectedTeam.name,
                    }).toString()}`
                  }
                >
                  Обновить из Liquipedia
                </Link>

                <button
                  className="button button--danger"
                  disabled={deletingTeam}
                  onClick={
                    () => void removeTeam()
                  }
                  type="button"
                >
                  {
                    deletingTeam
                      ? "Удаляем..."
                      : "Удалить команду"
                  }
                </button>
              </div>
            ) : null}
          </section>

          {selectedTeam ? (
            <>
              <section className="admin-roster-summary">
                <article>
                  <span>
                    Основной состав
                  </span>

                  <strong
                    className={
                      activeCount === 5
                        ? ""
                        : "text-danger"
                    }
                  >
                    {activeCount}/5
                  </strong>
                </article>

                <article>
                  <span>
                    Тренеры
                  </span>

                  <strong
                    className={
                      coachCount <= 1
                        ? ""
                        : "text-danger"
                    }
                  >
                    {coachCount}/1
                  </strong>
                </article>

                <article>
                  <span>
                    Сила состава
                  </span>

                  <strong>
                    {
                      selectedTeam
                        .strength
                        .team_strength_score
                    }%
                  </strong>
                </article>
              </section>

              <section className="panel section-panel">
                <div className="panel__heading">
                  <div>
                    <span className="panel__label">
                      Состав
                    </span>

                    <h2>
                      {selectedTeam.name}
                    </h2>
                  </div>

                  <button
                    className="button button--secondary"
                    onClick={addPlayer}
                    type="button"
                  >
                    Добавить игрока
                  </button>
                </div>

                <div className="admin-roster-list">
                  {rows.map(
                    (row) => {
                      const availableRoles =
                        roleOptions.filter(
                          (option) =>
                            option
                              .allowed_statuses
                              .includes(
                                row.status,
                              ),
                        );

                      return (
                        <article
                          className={
                            `admin-player-card${
                              row.deleted
                                ? " admin-player-card--deleted"
                                : ""
                            }`
                          }
                          key={row.key}
                        >
                          <div className="admin-player-card__header">
                            <strong>
                              {
                                row.nickname
                                || "Новый игрок"
                              }
                            </strong>

                            {row.deleted ? (
                              <button
                                className="button button--secondary"
                                onClick={
                                  () =>
                                    restorePlayer(row)
                                }
                                type="button"
                              >
                                Восстановить
                              </button>
                            ) : (
                              <button
                                className="button button--danger"
                                onClick={
                                  () =>
                                    markPlayerDeleted(
                                      row,
                                    )
                                }
                                type="button"
                              >
                                Удалить из состава
                              </button>
                            )}
                          </div>

                          {!row.deleted ? (
                            <div className="admin-player-grid">
                              <label>
                                <span>
                                  Никнейм
                                </span>

                                <input
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          nickname:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  type="text"
                                  value={
                                    row.nickname
                                  }
                                />
                              </label>

                              <label>
                                <span>
                                  Статус
                                </span>

                                <select
                                  onChange={(event) => {
                                      const status = parseRosterStatus(
                                        event.currentTarget.value,
                                      );

                                      changeStatus(
                                        row,
                                        status,
                                      );
                                    }}
                                  value={
                                    row.status
                                  }
                                >
                                  <option value="active">
                                    Основной состав
                                  </option>

                                  <option value="coach">
                                    Тренер
                                  </option>
                                </select>
                              </label>

                              <label>
                                <span>
                                  Роль
                                </span>

                                <select
                                  onChange={(event) => {
                                      const role = parseTeamRole(
                                        event.currentTarget.value,
                                      );

                                      changeRole(
                                        row,
                                        role,
                                      );
                                    }}
                                  value={row.role}
                                >
                                  <option value="">
                                    Выберите роль
                                  </option>

                                  {
                                    availableRoles.map(
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
                              </label>

                              <label>
                                <span>
                                  Настоящее имя
                                </span>

                                <input
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          realName:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  type="text"
                                  value={
                                    row.realName
                                  }
                                />
                              </label>

                              <label>
                                <span>
                                  Страна
                                </span>

                                <input
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          country:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  type="text"
                                  value={
                                    row.country
                                  }
                                />
                              </label>

                              <label>
                                <span>
                                  В составе с
                                </span>

                                <input
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          joinedAt:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  type="date"
                                  value={
                                    row.joinedAt
                                  }
                                />
                              </label>

                              <label>
                                <span>
                                  Рейтинг
                                </span>

                                <input
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          currentRating:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  step="0.01"
                                  type="number"
                                  value={
                                    row.currentRating
                                  }
                                />
                              </label>

                              <label>
                                <span>
                                  Сила игрока
                                </span>

                                <input
                                  max="100"
                                  min="0"
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          strengthScore:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  step="0.1"
                                  type="number"
                                  value={
                                    row.strengthScore
                                  }
                                />
                              </label>

                              <label className="admin-player-grid__notes">
                                <span>
                                  Примечание
                                </span>

                                <input
                                  onChange={
                                    (event) =>
                                      updateRow(
                                        row.key,
                                        {
                                          notes:
                                            event
                                              .target
                                              .value,
                                        },
                                      )
                                  }
                                  type="text"
                                  value={
                                    row.notes
                                  }
                                />
                              </label>
                            </div>
                          ) : (
                            <p>
                              Игрок будет удалён
                              после сохранения.
                            </p>
                          )}
                        </article>
                      );
                    },
                  )}
                </div>
              </section>

              <section className="panel save-import-panel">
                <div>
                  <h2>
                    Сохранение изменений
                  </h2>

                  <p>
                    После удаления или
                    добавления игроков в
                    основном составе должно
                    остаться ровно пять человек.
                  </p>

                  {!canSave ? (
                    <p className="save-import-panel__error">
                      Проверь количество игроков,
                      тренеров и назначенные роли.
                    </p>
                  ) : (
                    <p className="save-import-panel__ready">
                      Состав готов к сохранению.
                    </p>
                  )}
                </div>

                <button
                  className="button"
                  disabled={!canSave}
                  onClick={
                    () => void saveRoster()
                  }
                  type="button"
                >
                  {
                    saving
                      ? "Сохраняем..."
                      : "Сохранить состав"
                  }
                </button>
              </section>
            </>
          ) : null}
        </>
      )}
    </>
  );
}