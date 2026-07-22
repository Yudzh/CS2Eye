import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  demosApi,
} from "../api/demos";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/AsyncState";

import {
  formatDate,
  formatNumber,
} from "../lib/format";

import type {
  DemoParseRunListItem,
  DemoPlayerMapStat,
} from "../types";


function demoLabel(
  parseRun: DemoParseRunListItem,
): string {
  const teamA =
    parseRun.team_a_name || "Команда A";

  const teamB =
    parseRun.team_b_name || "Команда B";

  const map =
    parseRun.map_name || "карта неизвестна";

  return `${teamA} — ${teamB} · ${map}`;
}


export function DemoParseRunsPage() {
  const [
    parseRuns,
    setParseRuns,
  ] = useState<DemoParseRunListItem[]>([]);

  const [
    selectedParseRunId,
    setSelectedParseRunId,
  ] = useState("");

  const [
    players,
    setPlayers,
  ] = useState<DemoPlayerMapStat[]>([]);

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    playersLoading,
    setPlayersLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  useEffect(() => {
    async function loadParseRuns() {
      setLoading(true);
      setError(null);

      try {
        const response =
          await demosApi.listParseRuns();

        setParseRuns(response.items);

        setSelectedParseRunId(
          response.items[0]?.id || "",
        );
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Не удалось загрузить demo.",
        );
      } finally {
        setLoading(false);
      }
    }

    void loadParseRuns();
  }, []);


  useEffect(() => {
    if (!selectedParseRunId) {
      setPlayers([]);
      return;
    }

    async function loadPlayers() {
      setPlayersLoading(true);
      setError(null);

      try {
        const response =
          await demosApi.getPlayers(
            selectedParseRunId,
          );

        setPlayers(response.items);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Не удалось загрузить статистику игроков.",
        );
      } finally {
        setPlayersLoading(false);
      }
    }

    void loadPlayers();
  }, [selectedParseRunId]);


  const selectedParseRun = useMemo(
    () =>
      parseRuns.find(
        (parseRun) =>
          parseRun.id === selectedParseRunId,
      ) || null,
    [
      parseRuns,
      selectedParseRunId,
    ],
  );


  if (loading) {
    return (
      <LoadingState message="Загружаем импортированные demo..." />
    );
  }


  if (error) {
    return <ErrorState message={error} />;
  }


  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            Demo-статистика
          </p>

          <h1>Статистика игроков</h1>

          <p className="page-heading__description">
            Урон и ADR игроков на каждой
            распарсенной карте.
          </p>
        </div>
      </section>

      {parseRuns.length === 0 ? (
        <EmptyState message="Успешно распарсенных demo пока нет." />
      ) : (
        <>
          <section className="panel">
            <div className="admin-team-selector">
              <label>
                <span>Выберите карту</span>

                <select
                  onChange={(event) =>
                    setSelectedParseRunId(
                      event.target.value,
                    )
                  }
                  value={selectedParseRunId}
                >
                  {parseRuns.map((parseRun) => (
                    <option
                      key={parseRun.id}
                      value={parseRun.id}
                    >
                      {demoLabel(parseRun)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {selectedParseRun ? (
              <p className="panel__note">
                Турнир:{" "}
                {selectedParseRun.tournament_name || "—"}

                {" · "}

                Дата:{" "}
                {formatDate(
                  selectedParseRun.match_date,
                )}

                {" · "}

                Раундов:{" "}
                {selectedParseRun.rounds_count ?? "—"}
              </p>
            ) : null}
          </section>

          <section className="panel section-panel">
            <div className="panel__heading">
              <div>
                <span className="panel__label">
                  Игроки карты
                </span>

                <h2>
                  Индивидуальная статистика
                </h2>
              </div>

              <span className="table-count">
                {players.length}
              </span>
            </div>

            {playersLoading ? (
              <LoadingState message="Загружаем игроков..." />
            ) : players.length === 0 ? (
              <EmptyState message="Статистика игроков не найдена. Старые demo нужно импортировать повторно." />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Игрок</th>
                      <th>Команда</th>
                      <th>Раунды</th>
                      <th>Общий урон</th>
                      <th>ADR</th>
                      <th>Связь</th>
                    </tr>
                  </thead>

                  <tbody>
                    {players.map((player) => (
                      <tr
                        key={
                          `${player.team_name}-${player.player_name}`
                        }
                      >
                        <td>
                          <strong>
                            {player.player_name}
                          </strong>
                        </td>

                        <td>
                          {player.team_name || "—"}
                        </td>

                        <td>
                          {player.rounds_count}
                        </td>

                        <td>
                          {player.total_damage}
                        </td>

                        <td>
                          <strong>
                            {formatNumber(
                              player.average_damage_per_round,
                            )}
                          </strong>
                        </td>

                        <td>
                          <span
                            className={
                              player.player_id
                                ? "status-badge status-badge--stable"
                                : "status-badge status-badge--unknown"
                            }
                          >
                            {player.player_id
                              ? "Связан"
                              : "Не связан"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}