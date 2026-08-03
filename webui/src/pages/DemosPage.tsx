import { FormEvent, useEffect, useState } from "react";

import { getDemoFiles, getDemoMapResult, getDemoMaps, getDemoPlayerStats, getDemoRounds, getDemoSideStats, getDemoTournaments, getTeams, parseDemoFile, parseDemoFiles, patchDemoMapResult, recalculateDemoSideStats, reclassifyDemoOpponentRanks, reclassifyOpponentRanks, uploadDemoFiles } from "../api";
import type { DemoListResponse, DemoMapOption, DemoMapResult, DemoMapResultPatch, DemoParseResponse, DemoPlayerStatsResponse, DemoRoundsResponse, DemoSideStatsResponse, DemoTournamentOption, DemoUploadResponse, DemoUploadStatus, Team } from "../types";


const statusLabels: Record<DemoUploadStatus, string> = {
  created: "Добавлена",
  replaced: "Заменена",
  unchanged: "Без изменений",
  failed: "Ошибка",
};
const parseStatusLabels = {
  pending: "Не обработана", processing: "Обрабатывается",
  success: "Обработана", failed: "Ошибка",
};
const opponentGroupLabels = {
  top_15: "Top 1–15", top_16_30: "Top 16–30",
  outside_top_30: "Вне Top 30", unknown: "Соперник не определён",
};
const opponentSourceLabels = {
  historical_snapshot: "Исторический рейтинг",
  current_fallback: "Текущий рейтинг — исторических данных нет",
  unknown: "Рейтинг не найден",
};
const metadataLabels = {
  complete: "Данные определены", needs_review: "Требуется проверка",
  partial: "Неполные данные", invalid: "Некорректные данные",
};
const roundStatusLabels = {
  not_parsed: "CT/T данные: ещё не разобраны", complete: "Раунды разобраны полностью",
  partial: "Раунды разобраны частично", needs_review: "CT/T данные: требуется проверка",
  invalid: "Раундовые данные некорректны",
};
const reasonLabels: Record<string, string> = {
  target_bombed: "Бомба взорвалась", bomb_defused: "Бомба обезврежена",
  terrorists_eliminated: "T уничтожены", cts_eliminated: "CT уничтожены",
  target_saved: "Время истекло", hostages_rescued: "Заложники спасены",
  terrorists_escaped: "T ушли", game_commencing: "Начало игры", draw: "Ничья", unknown: "Причина неизвестна",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} КБ`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} МБ`;
  return `${(bytes / 1024 ** 3).toFixed(2)} ГБ`;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Не удалось выполнить запрос.";
}

function formatDiagnostic(value: string): string {
  let match = value.match(/^incomplete_round_skipped:raw_round=(.*):tick=(.*)$/);
  if (match) return `Пропущено незавершённое служебное событие раунда (raw №${match[1]}, tick ${match[2]}).`;
  match = value.match(/^duplicate_round_event:raw_round=(.*):tick=(.*)$/);
  if (match) return `Повторное событие raw-раунда №${match[1]} на tick ${match[2]} пропущено.`;
  match = value.match(/^restart_round_skipped:raw_round=(.*):tick=(.*)$/);
  if (match) return `Событие рестарта raw-раунда №${match[1]} на tick ${match[2]} не включено в статистику.`;
  match = value.match(/^restart_round_skipped:score_reset_at_raw_round=(.*):discarded=(\d+)$/);
  if (match) return `Обнаружен сброс счёта перед raw-раундом №${match[1]}: отброшено служебных/knife-раундов — ${match[2]}.`;
  match = value.match(/^round_score_mismatch:round=(\d+):raw=(\d+):(\d+):calculated=(\d+):(\d+)$/);
  if (match) return `Раунд ${match[1]}: parser показывает ${match[2]}:${match[3]}, последовательный расчёт — ${match[4]}:${match[5]}.`;
  match = value.match(/^round_count_mismatch:parsed=(\d+):expected=(\d+|None)$/);
  if (match) return `Число валидных раундов: распознано ${match[1]}, ожидалось ${match[2]}.`;
  match = value.match(/^final_score_mismatch:parsed=(\d+):(\d+):expected=(\d+|None):(\d+|None)$/);
  if (match) return `Сумма побед по раундам ${match[1]}:${match[2]}, итог карты ${match[3]}:${match[4]}.`;
  if (value.startsWith("Demo team \"") && value.includes("was not found")) return value.replace("Demo team", "Команда из демки").replace("was not found in teams.", "не найдена во внутреннем справочнике teams.");
  const labels: Record<string, string> = {
    team_not_resolved: "Хотя бы одна команда не связана с внутренним справочником.",
    unknown_round_side: "Не удалось определить CT/T сторону команды в одном или нескольких раундах.",
    unknown_round_winner: "Не удалось определить победителя одного или нескольких раундов.",
    unknown_end_reason: "Parser вернул неизвестную причину завершения раунда.",
    incomplete_round_skipped: "Незавершённое служебное событие раунда пропущено.",
    duplicate_round_event: "Повторное событие завершения раунда пропущено.",
    round_score_mismatch: "Обнаружено расхождение счёта внутри последовательности раундов.",
    round_count_mismatch: "Количество валидных раундов не совпадает с итогом карты.",
    final_score_mismatch: "Победы по раундам не совпадают с финальным счётом.",
  };
  return labels[value] || value;
}

function detailedDiagnostics(items: string[]): string[] {
  const unique = Array.from(new Set(items));
  return unique.filter((item) => {
    if (["incomplete_round_skipped", "duplicate_round_event", "restart_round_skipped"].some((code) => item === code || item.startsWith(`${code}:`))) return false;
    if (item.includes(":")) return true;
    if (item === "team_not_resolved" && unique.some((other) => other.startsWith("Demo team \""))) return false;
    return !unique.some((other) => other.startsWith(`${item}:`));
  });
}

export function DemosPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [tournament, setTournament] = useState("");
  const [eventType, setEventType] = useState<"online" | "lan">("online");
  const [matchDate, setMatchDate] = useState(today);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<DemoUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [filterTournament, setFilterTournament] = useState("");
  const [tournaments, setTournaments] = useState<DemoTournamentOption[]>([]);
  const [year, setYear] = useState(new Date().getFullYear());
  const [loadingList, setLoadingList] = useState(false);
  const [listResult, setListResult] = useState<DemoListResponse | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [parsingMode, setParsingMode] = useState<"new" | "all" | null>(null);
  const [parsingFileId, setParsingFileId] = useState<number | null>(null);
  const [parseResult, setParseResult] = useState<DemoParseResponse | null>(null);
  const [playerStats, setPlayerStats] = useState<DemoPlayerStatsResponse | null>(null);
  const [rankSourceFilter, setRankSourceFilter] = useState("all");
  const [reclassifying, setReclassifying] = useState(false);
  const [reclassifyMessage, setReclassifyMessage] = useState<string | null>(null);
  const [mapResult, setMapResult] = useState<DemoMapResult | null>(null);
  const [editingResult, setEditingResult] = useState(false);
  const [mapForm, setMapForm] = useState<DemoMapResultPatch | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [maps, setMaps] = useState<DemoMapOption[]>([]);
  const [sideStats, setSideStats] = useState<DemoSideStatsResponse | null>(null);
  const [rounds, setRounds] = useState<DemoRoundsResponse | null>(null);
  const [roundFilter, setRoundFilter] = useState("all");
  const [roundsOpen, setRoundsOpen] = useState(false);

  useEffect(() => {
    void getDemoTournaments().then(setTournaments).catch((error) => setListError(message(error)));
    void getTeams().then(setTeams).catch(() => undefined);
    void getDemoMaps().then((result) => setMaps(result.items)).catch(() => undefined);
  }, []);

  async function submitUpload(event: FormEvent) {
    event.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      setUploadResult(await uploadDemoFiles(tournament, eventType, matchDate, files));
      try {
        setTournaments(await getDemoTournaments());
      } catch (error) {
        setListError(message(error));
      }
    } catch (error) {
      setUploadError(message(error));
    } finally {
      setUploading(false);
    }
  }

  async function parseAll(replaceExisting = false) {
    setParsingMode(replaceExisting ? "all" : "new");
    setListError(null);
    try {
      setParseResult(await parseDemoFiles(filterTournament, year, replaceExisting));
      setListResult(await getDemoFiles(filterTournament, year));
    } catch (error) {
      setListError(message(error));
    } finally {
      setParsingMode(null);
    }
  }

  async function parseOne(id: number, replace: boolean) {
    setParsingFileId(id);
    setListError(null);
    try {
      const result = await parseDemoFile(id, replace);
      setParseResult({
        tournament_name: filterTournament, year, total_files: 1,
        parsed_count: result.status === "parsed" ? 1 : 0,
        skipped_count: result.status === "skipped" ? 1 : 0,
        failed_count: result.status === "failed" ? 1 : 0,
        players_recalculated: result.players_linked,
        files: [result],
      });
      setPlayerStats(await getDemoPlayerStats(id));
      setMapResult(await getDemoMapResult(id));
      setSideStats(await getDemoSideStats(id));
      setRounds(await getDemoRounds(id));
      setListResult(await getDemoFiles(filterTournament, year));
    } catch (error) {
      setListError(message(error));
    } finally {
      setParsingFileId(null);
    }
  }

  async function showPlayerStats(id: number) {
    setParsingFileId(id);
    setListError(null);
    try {
      setPlayerStats(await getDemoPlayerStats(id));
      setMapResult(await getDemoMapResult(id));
      setSideStats(await getDemoSideStats(id));
      setRounds(await getDemoRounds(id));
    } catch (error) {
      setListError(message(error));
    } finally {
      setParsingFileId(null);
    }
  }

  async function changeRoundFilter(filter: string) {
    if (!mapResult) return;
    setRoundFilter(filter);
    try { setRounds(await getDemoRounds(mapResult.demo_file_id, filter)); }
    catch (error) { setListError(message(error)); }
  }

  async function recalculateSides() {
    if (!mapResult) return;
    try {
      setSideStats(await recalculateDemoSideStats(mapResult.demo_file_id));
      setMapResult(await getDemoMapResult(mapResult.demo_file_id));
      setListResult(await getDemoFiles(filterTournament, year));
    } catch (error) { setListError(message(error)); }
  }

  function startEdit(result: DemoMapResult) {
    setMapForm({ map_name: result.map_name, team_a_id: result.team_a.id, team_a_name: result.team_a.name, team_a_score: result.team_a.score, team_b_id: result.team_b.id, team_b_name: result.team_b.name, team_b_score: result.team_b.score });
    setEditingResult(true);
  }

  async function saveMapResult(event: FormEvent) {
    event.preventDefault();
    if (!mapResult || !mapForm) return;
    try {
      setMapResult(await patchDemoMapResult(mapResult.demo_file_id, mapForm));
      setEditingResult(false);
      setListResult(await getDemoFiles(filterTournament, year));
    } catch (error) { setListError(message(error)); }
  }

  async function reclassifyAll() {
    setReclassifying(true);
    setListError(null);
    try {
      const result = await reclassifyOpponentRanks(filterTournament, year, false);
      setReclassifyMessage(`Проверено: ${result.player_stats_checked}, обновлено: ${result.updated_count}, без изменений: ${result.unchanged_count}, ошибок: ${result.failed_count}.`);
      if (playerStats) setPlayerStats(await getDemoPlayerStats(playerStats.demo_file_id));
    } catch (error) {
      setListError(message(error));
    } finally {
      setReclassifying(false);
    }
  }

  async function reclassifyOne(id: number) {
    setParsingFileId(id);
    setListError(null);
    try {
      const result = await reclassifyDemoOpponentRanks(id);
      setReclassifyMessage(`Обновлено строк: ${result.updated_count}; пересчитано игроков: ${result.players_recalculated}.`);
      setPlayerStats(await getDemoPlayerStats(id));
    } catch (error) {
      setListError(message(error));
    } finally {
      setParsingFileId(null);
    }
  }

  async function submitList(event: FormEvent) {
    event.preventDefault();
    setLoadingList(true);
    setListError(null);
    try {
      setListResult(await getDemoFiles(filterTournament, year));
    } catch (error) {
      setListError(message(error));
      setListResult(null);
    } finally {
      setLoadingList(false);
    }
  }

  return (
    <main className="page demos-page">
      <nav className="page-links"><a className="back-link" href="/">← К командам</a></nav>
      <section className="demo-heading">
        <p className="eyebrow">Файловое хранилище</p>
        <h1>Демки</h1>
        <p className="lead">Загрузка, хранение и расчёт внутреннего рейтинга игроков по CS2 demo.</p>
      </section>

      <div className="demo-grid">
        <section className="demo-panel">
          <div className="section-heading"><div><p className="eyebrow">Добавление</p><h2>Загрузить демки</h2></div></div>
          <form className="demo-form" onSubmit={(event) => void submitUpload(event)}>
            <label>Название турнира<input required value={tournament} onChange={(event) => setTournament(event.target.value)} placeholder="IEM Cologne" /></label>
            <label>Формат турнира<select value={eventType} onChange={(event) => setEventType(event.target.value as "online" | "lan")}><option value="online">Online</option><option value="lan">LAN</option></select></label>
            <label>Дата матчей<input required type="date" value={matchDate} onChange={(event) => setMatchDate(event.target.value)} /></label>
            <label>Demo-файлы или архивы<input required multiple accept=".dem,.zip,.rar" type="file" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label>
            {files.length > 0 && <ul className="selected-files">{files.map((file) => <li key={`${file.name}-${file.size}`}>{file.name}<small>{formatSize(file.size)}</small></li>)}</ul>}
            <button className="button button--primary" disabled={uploading || files.length === 0} type="submit">{uploading ? "Загружаю…" : "Загрузить"}</button>
          </form>
          {uploadError && <div className="notice notice--error">{uploadError}</div>}
          {uploadResult && <div className="demo-results">{uploadResult.files.map((file, index) => <div className={`demo-result demo-result--${file.status}`} key={`${file.filename}-${index}`}><div><strong>{file.filename}</strong><small>{file.error || (file.file_size_bytes !== null ? formatSize(file.file_size_bytes) : "")}</small></div><span>{statusLabels[file.status]}</span></div>)}</div>}
        </section>

        <section className="demo-panel">
          <div className="section-heading"><div><p className="eyebrow">Хранилище</p><h2>Просмотр демок</h2></div></div>
          <form className="demo-form demo-filter" onSubmit={(event) => void submitList(event)}>
            <label>Название турнира<select required value={filterTournament} onChange={(event) => setFilterTournament(event.target.value)}><option value="">Выберите турнир</option>{tournaments.map((item) => <option key={item.slug} value={item.name}>{item.name}</option>)}</select></label>
            <label>Год<input required min="2000" max="2100" type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
            <button className="button" disabled={loadingList} type="submit">{loadingList ? "Загружаю…" : "Показать демки"}</button>
          </form>
          {listError && <div className="notice notice--error">{listError}</div>}
          {listResult && <div className="demo-list">
            <div className="demo-parse-actions">
              <h3>{listResult.tournament_name} · {listResult.year}</h3>
              <button className="button button--primary" disabled={parsingMode !== null || listResult.total_files === 0} onClick={() => void parseAll()}>{parsingMode === "new" ? "Парсинг…" : "Распарсить рейтинг игроков"}</button>
              <button className="button" disabled={parsingMode !== null || listResult.total_files === 0} onClick={() => void parseAll(true)}>{parsingMode === "all" ? "Повторный парсинг…" : "Перепарсить все демки"}</button>
              <button className="button" disabled={reclassifying || listResult.total_files === 0} onClick={() => void reclassifyAll()}>{reclassifying ? "Обновляю…" : "Обновить историческую классификацию"}</button>
            </div>
            {reclassifyMessage && <div className="notice">{reclassifyMessage}</div>}
            {parseResult && <><div className="parse-summary"><span>Обработано: {parseResult.parsed_count}</span><span>Пропущено: {parseResult.skipped_count}</span><span>Ошибок: {parseResult.failed_count}</span><span>Найдено игроков: {parseResult.files.reduce((sum, file) => sum + file.players_found, 0)}</span><span>Связано: {parseResult.files.reduce((sum, file) => sum + file.players_linked, 0)}</span><span>Не связано: {parseResult.files.reduce((sum, file) => sum + file.players_unlinked, 0)}</span></div>{parseResult.files.map((file) => { const visible = detailedDiagnostics(file.diagnostics); return visible.length > 0 ? <div className="notice notice--warning" key={`diagnostics-${file.demo_file_id}`}><strong>{file.filename}</strong>{visible.map((diagnostic) => <div key={diagnostic}>{formatDiagnostic(diagnostic)}</div>)}</div> : null; })}{parseResult.files.flatMap((file) => file.unlinked_players).length > 0 && <div className="unlinked-players"><strong>Нераспознанные игроки</strong>{parseResult.files.flatMap((file) => file.unlinked_players).map((player, index) => <span key={`${player.demo_filename}-${player.steam_id}-${index}`}>{player.nickname} · {player.steam_id || "Steam ID нет"} · {player.team_name || "команда не указана"} · {player.demo_filename}</span>)}</div>}</>}
            {playerStats && <div className="opponent-classification">
              <strong>{playerStats.filename}</strong>
              <label>Источник рейтинга<select value={rankSourceFilter} onChange={(event) => setRankSourceFilter(event.target.value)}><option value="all">Все источники</option><option value="historical_snapshot">Исторический рейтинг</option><option value="current_fallback">Текущий fallback</option><option value="unknown">Не определено</option></select></label>
              <div className="opponent-classification__head"><span>Игрок</span><span>Соперник</span><span>Место / группа</span><span>Источник рейтинга</span><span>Дата snapshot</span></div>
              {playerStats.players.filter((player) => rankSourceFilter === "all" || player.opponent_rank_source === rankSourceFilter).map((player, index) => <div key={`${player.steam_id}-${index}`}><span>{player.nickname}</span><span>{player.opponent_team_name || "—"}</span><span>{player.opponent_rank === null ? "—" : `${player.opponent_rank} место`} · {opponentGroupLabels[player.opponent_rank_group]}</span><span>{opponentSourceLabels[player.opponent_rank_source]}</span><span>{player.opponent_rank_snapshot_date ? new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC" }).format(new Date(`${player.opponent_rank_snapshot_date}T00:00:00Z`)) : "—"}</span></div>)}
            </div>}
            {mapResult && <section className="map-result-card">
              <p className="eyebrow">Результат карты</p>
              <h3>{mapResult.map_name ? mapResult.map_name[0].toUpperCase() + mapResult.map_name.slice(1) : "Карта не определена"}</h3>
              <div className="map-result-score"><span>{mapResult.team_a.name || "Команда A"}</span><strong>{mapResult.team_a.score ?? "—"}</strong><span>{mapResult.team_b.name || "Команда B"}</span><strong>{mapResult.team_b.score ?? "—"}</strong></div>
              <p>Победитель: {mapResult.winner?.name || "—"}</p>
              <p>Раунды: {mapResult.rounds_count ?? "—"} · Overtime: {mapResult.went_to_overtime === null ? "—" : mapResult.went_to_overtime ? "да" : "нет"}</p>
              <p>Источник: {mapResult.result_source === "demo_parser" ? "данные демки" : mapResult.result_source === "manual_override" ? "ручное исправление" : "смешанный"} · {metadataLabels[mapResult.metadata_status]}</p>
              {mapResult.issues.map((issue) => <div className="notice notice--warning" key={issue}>{issue}</div>)}
              {mapResult.metadata_status !== "complete" && <button className="button" onClick={() => startEdit(mapResult)}>Исправить результат</button>}
              {editingResult && mapForm && <form className="demo-form map-result-form" onSubmit={(event) => void saveMapResult(event)}>
                <label>Карта<select value={mapForm.map_name ?? ""} onChange={(event) => setMapForm({ ...mapForm, map_name: event.target.value || null })}><option value="">Не выбрана</option>{maps.map((map) => <option key={map.code} value={map.code}>{map.title}</option>)}</select></label>
                {(["a", "b"] as const).map((side) => <fieldset key={side}><legend>Команда {side.toUpperCase()}</legend><label>Команда из БД<select value={mapForm[`team_${side}_id`] ?? ""} onChange={(event) => { const team = teams.find((item) => item.id === Number(event.target.value)); setMapForm({ ...mapForm, [`team_${side}_id`]: team?.id ?? null, [`team_${side}_name`]: team?.name ?? mapForm[`team_${side}_name`] }); }}><option value="">Только текстовое название</option>{teams.map((team) => <option key={team.id} value={team.id}>{team.current_rank ? `${team.current_rank}. ` : ""}{team.name}</option>)}</select></label><label>Название<input value={mapForm[`team_${side}_name`] ?? ""} onChange={(event) => setMapForm({ ...mapForm, [`team_${side}_name`]: event.target.value || null })} /></label><label>Счёт<input min="0" type="number" value={mapForm[`team_${side}_score`] ?? ""} onChange={(event) => setMapForm({ ...mapForm, [`team_${side}_score`]: event.target.value === "" ? null : Number(event.target.value) })} /></label></fieldset>)}
                <button className="button button--primary" type="submit">Сохранить</button>
              </form>}
            </section>}
            {sideStats && <section className="map-result-card">
              <p className="eyebrow">Статистика сторон</p>
              <h3>{roundStatusLabels[sideStats.round_data_status]}</h3>
              {mapResult && <p>{mapResult.rounds_parsed_count} из {mapResult.rounds_expected_count ?? "—"} раундов</p>}
              <div className="side-stats-grid">{sideStats.teams.map((team) => <article key={`${team.team_id}-${team.team_name}`}><h4>{team.team_name}</h4><div className="side-stat-row"><strong>CT</strong><span>{team.ct.rounds_won} / {team.ct.rounds_played}</span><span>{team.ct.win_rate === null ? "—" : `${Number(team.ct.win_rate).toFixed(1)}%`}</span></div><div className="side-stat-row"><strong>T</strong><span>{team.t.rounds_won} / {team.t.rounds_played}</span><span>{team.t.win_rate === null ? "—" : `${Number(team.t.win_rate).toFixed(1)}%`}</span></div><p>Первая половина: {team.first_half.rounds_won} / {team.first_half.rounds_played}</p><p>Вторая половина: {team.second_half.rounds_won} / {team.second_half.rounds_played}</p>{team.overtime.rounds_played > 0 && <p>Overtime: {team.overtime.rounds_won} / {team.overtime.rounds_played}</p>}</article>)}</div>
              <button className="button" onClick={() => void recalculateSides()}>Пересчитать CT/T из раундов</button>
            </section>}
            {rounds && <section className="map-result-card">
              <button className="button" onClick={() => setRoundsOpen(!roundsOpen)}>{roundsOpen ? "Скрыть раунды" : `Раунды (${rounds.total})`}</button>
              {roundsOpen && <><div className="round-filters">{[["all", "Все"], ["regulation", "Основное время"], ["overtime", "Overtime"], ["CT", "Победа CT"], ["T", "Победа T"]].map(([value, label]) => <button className={`button ${roundFilter === value ? "button--primary" : ""}`} key={value} onClick={() => void changeRoundFilter(value)}>{label}</button>)}</div><div className="rounds-table"><div className="rounds-table__head"><span>№</span><span>Половина</span><span>Стороны</span><span>Победитель</span><span>Причина</span><span>Счёт</span><span>Длительность</span></div>{rounds.items.map((round) => <div key={round.round_number}><span>{round.round_number}</span><span>{round.half === "first_half" ? "1-я" : round.half === "second_half" ? "2-я" : "OT"}</span><span>{mapResult?.team_a.name} {round.team_a_side} / {mapResult?.team_b.name} {round.team_b_side}</span><span>{round.winner_team_name || "—"}</span><span>{reasonLabels[round.end_reason] || reasonLabels.unknown}</span><span>{round.team_a_score_after ?? "—"}:{round.team_b_score_after ?? "—"}</span><span>{round.duration_seconds === null ? "—" : `${Math.round(Number(round.duration_seconds))} сек`}</span></div>)}</div></>}
            </section>}
            {listResult.dates.length === 0 ? <div className="empty-state">Демок не найдено.</div> : listResult.dates.map((group) => <section key={group.match_date}><h4>{new Intl.DateTimeFormat("ru-RU", { dateStyle: "long", timeZone: "UTC" }).format(new Date(`${group.match_date}T00:00:00Z`))}</h4>{group.files.map((file) => <div className="stored-demo" key={file.id}><strong>{file.filename}</strong>{file.map_name ? <><span>{file.map_name[0].toUpperCase() + file.map_name.slice(1)} · {file.team_a_name || "—"} {file.team_a_score ?? "—"}:{file.team_b_score ?? "—"} {file.team_b_name || "—"}</span><span>Победитель: {file.winner_team_name || "—"} · {file.metadata_status ? metadataLabels[file.metadata_status] : ""}</span><span>{file.round_data_status ? roundStatusLabels[file.round_data_status] : "CT/T данные: ещё не разобраны"}</span></> : <span>Результат ещё не определён</span>}<span>{formatSize(file.file_size_bytes)} · {parseStatusLabels[file.parse_status]}</span><div className="stored-demo__action"><code>{file.sha256.slice(0, 12)}…</code>{file.parse_status === "success" && <><button className="button" disabled={parsingFileId === file.id} onClick={() => void showPlayerStats(file.id)}>Результат и игроки</button><button className="button" disabled={parsingFileId === file.id} onClick={() => void reclassifyOne(file.id)}>Обновить классификацию</button></>}<button className="button" disabled={parsingFileId === file.id} onClick={() => void parseOne(file.id, file.parse_status === "success")}>{parsingFileId === file.id ? "Обработка…" : file.parse_status === "success" ? "Повторить парсинг" : "Распарсить"}</button></div></div>)}</section>)}
          </div>}
        </section>
      </div>
    </main>
  );
}
