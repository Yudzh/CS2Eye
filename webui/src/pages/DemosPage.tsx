import { FormEvent, useEffect, useState } from "react";

import { getDemoBombStats, getDemoCombatStats, getDemoUtilityStats, getDemoEconomyStats, getDemoFiles, getDemoMapResult, getDemoMaps, getDemoPlayerStats, getDemoRounds, getDemoSideStats, getDemoTournaments, getParseAllDemoJob, getTeams, parseDemoFile, patchDemoMapResult, recalculateDemoSideStats, reclassifyDemoOpponentRanks, reclassifyOpponentRanks, startFilteredDemoParseJob, startParseAllDemoJob, uploadDemoFiles } from "../api";
import type { DemoBombStatsResponse, DemoCombatStatsResponse, DemoUtilityStatsResponse, DemoEconomyStatsResponse, DemoListResponse, DemoMapOption, DemoMapResult, DemoMapResultPatch, DemoParseJob, DemoParseResponse, DemoPlayerStatsResponse, DemoRoundsResponse, DemoSideStatsResponse, DemoTournamentOption, DemoUploadResponse, DemoUploadStatus, Team } from "../types";


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
    if (["incomplete_round_skipped", "duplicate_round_event", "restart_round_skipped", "incomplete_split_demo"].some((code) => item === code || item.startsWith(`${code}:`))) return false;
    if (item.includes(":")) return true;
    if (item === "team_not_resolved" && unique.some((other) => other.startsWith("Demo team \""))) return false;
    return !unique.some((other) => other.startsWith(`${item}:`));
  });
}

function diagnosticGroupKey(value: string): string {
  if (/^Demo team ".*" was not found/.test(value)) return "team_not_found";
  return value.split(":", 1)[0];
}

function GroupedDiagnostics({ files }: { files: DemoParseResponse["files"] }) {
  const groups = new Map<string, Array<{ filename: string; diagnostic: string }>>();
  files.forEach((file) => detailedDiagnostics(file.diagnostics).forEach((diagnostic) => {
    const key = diagnosticGroupKey(diagnostic);
    const entries = groups.get(key) ?? [];
    if (!entries.some((entry) => entry.filename === file.filename && entry.diagnostic === diagnostic)) {
      entries.push({ filename: file.filename, diagnostic });
    }
    groups.set(key, entries);
  }));
  return <>{Array.from(groups.entries()).map(([key, entries]) => {
    const title = key === "team_not_found"
      ? "Команда из demo отсутствует во внутреннем справочнике"
      : formatDiagnostic(key);
    const filesCount = new Set(entries.map((entry) => entry.filename)).size;
    return <details className="notice notice--warning" key={`diagnostic-group-${key}`}>
      <summary><strong>{title}</strong> · {filesCount} demo · {entries.length} сообщений</summary>
      <div className="diagnostic-group-list">{entries.map((entry, index) => <div key={`${entry.filename}-${entry.diagnostic}-${index}`}><strong>{entry.filename}</strong>{entry.diagnostic === key ? null : <span>{formatDiagnostic(entry.diagnostic)}</span>}</div>)}</div>
    </details>;
  })}</>;
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
  const [parseAfterUpload, setParseAfterUpload] = useState(false);
  const [filterTournament, setFilterTournament] = useState("");
  const [tournaments, setTournaments] = useState<DemoTournamentOption[]>([]);
  const [year, setYear] = useState(new Date().getFullYear());
  const [loadingList, setLoadingList] = useState(false);
  const [listResult, setListResult] = useState<DemoListResponse | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [parsingMode, setParsingMode] = useState<"new" | "selected" | "global" | null>(null);
  const [parsingFileId, setParsingFileId] = useState<number | null>(null);
  const [parseResult, setParseResult] = useState<DemoParseResponse | null>(null);
  const [parseJob, setParseJob] = useState<DemoParseJob | null>(null);
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
  const [bombStats, setBombStats] = useState<DemoBombStatsResponse | null>(null);
  const [economyStats, setEconomyStats] = useState<DemoEconomyStatsResponse | null>(null);
  const [combatStats, setCombatStats] = useState<DemoCombatStatsResponse | null>(null);
  const [utilityStats, setUtilityStats] = useState<DemoUtilityStatsResponse | null>(null);
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
      const result = await uploadDemoFiles(tournament, eventType, matchDate, files, parseAfterUpload);
      setUploadResult(result);
      if (result.parse_job_id) {
        let job = await getParseAllDemoJob(result.parse_job_id);
        setParseJob(job);
        while (job.status === "queued" || job.status === "running") {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          job = await getParseAllDemoJob(result.parse_job_id);
          setParseJob(job);
        }
      }
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
    setParsingMode(replaceExisting ? "selected" : "new");
    setListError(null);
    try {
      let job = await startFilteredDemoParseJob(filterTournament, year, replaceExisting);
      setParseJob(job);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        job = await getParseAllDemoJob(job.job_id);
        setParseJob(job);
      }
      if (job.status === "failed") throw new Error(job.error || "Парсинг завершился с ошибкой.");
      if (job.result) setParseResult(job.result);
      setListResult(await getDemoFiles(filterTournament, year));
    } catch (error) {
      setListError(message(error));
    } finally {
      setParsingMode(null);
    }
  }

  async function parseEveryDemo() {
    setParsingMode("global");
    setListError(null);
    try {
      let job = await startParseAllDemoJob();
      setParseJob(job);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        job = await getParseAllDemoJob(job.job_id);
        setParseJob(job);
      }
      if (job.status === "failed") throw new Error(job.error || "Массовый парсинг завершился с ошибкой.");
      if (job.result) setParseResult(job.result);
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
      setBombStats(await getDemoBombStats(id));
      setEconomyStats(await getDemoEconomyStats(id));
      setCombatStats(await getDemoCombatStats(id));
      setUtilityStats(await getDemoUtilityStats(id));
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
      setBombStats(await getDemoBombStats(id));
      setEconomyStats(await getDemoEconomyStats(id));
      setCombatStats(await getDemoCombatStats(id));
      setUtilityStats(await getDemoUtilityStats(id));
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
      <nav className="page-links"><a className="back-link" href="/">← К командам</a><a className="back-link" href="/matches">Матчи и предполагаемые серии →</a></nav>
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
            <label className="checkbox-label"><input type="checkbox" checked={parseAfterUpload} onChange={(event) => setParseAfterUpload(event.target.checked)} />Сразу парсить успешно загруженные демки</label>
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
              <button className="button" disabled={parsingMode !== null || listResult.total_files === 0} onClick={() => void parseAll(true)}>{parsingMode === "selected" ? "Повторный парсинг…" : "Перепарсить эти демки"}</button>
              <button className="button" disabled={parsingMode !== null} onClick={() => void parseEveryDemo()}>{parsingMode === "global" ? "Повторный парсинг всех демок…" : "Перепарсить ВСЕ демки"}</button>
              <button className="button" disabled={reclassifying || listResult.total_files === 0} onClick={() => void reclassifyAll()}>{reclassifying ? "Обновляю…" : "Обновить историческую классификацию"}</button>
            </div>
            {parsingMode !== null && parseJob && <div className="demo-parse-progress"><div><strong>{parseJob.processed_files}/{parseJob.total_files || "?"} файлов</strong><span>Успешно: {parseJob.parsed_count} · Пропущено: {parseJob.skipped_count} · Ошибок: {parseJob.failed_count}</span></div><progress max={parseJob.total_files || 1} value={parseJob.processed_files} />{parseJob.current_filename && <small>{parseJob.current_filename}</small>}</div>}
            {reclassifyMessage && <div className="notice">{reclassifyMessage}</div>}
            {parseResult && <><div className="parse-summary"><span>Обработано: {parseResult.parsed_count}</span><span>Пропущено: {parseResult.skipped_count}</span><span>Ошибок: {parseResult.failed_count}</span><span>Найдено игроков: {parseResult.files.reduce((sum, file) => sum + file.players_found, 0)}</span><span>Связано: {parseResult.files.reduce((sum, file) => sum + file.players_linked, 0)}</span><span>Не связано: {parseResult.files.reduce((sum, file) => sum + file.players_unlinked, 0)}</span></div>{parseResult.files.filter((file) => file.status === "failed").map((file) => <div className="notice notice--error" key={`error-${file.demo_file_id}`}><strong>{file.filename}</strong><div>{file.error || "Неизвестная ошибка парсинга."}</div></div>)}<GroupedDiagnostics files={parseResult.files} />{parseResult.files.flatMap((file) => file.unlinked_players).length > 0 && <div className="unlinked-players"><strong>Нераспознанные игроки</strong>{parseResult.files.flatMap((file) => file.unlinked_players).map((player, index) => <span key={`${player.demo_filename}-${player.steam_id}-${index}`}>{player.nickname} · {player.steam_id || "Steam ID нет"} · {player.team_name || "команда не указана"} · {player.demo_filename}</span>)}</div>}</>}
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
            {bombStats && <section className="map-result-card">
              <p className="eyebrow">Bomb / Postplant</p>
              {bombStats.bomb_data_status === "not_parsed" ? <div className="notice notice--warning">Для этой demo bomb analytics ещё не рассчитана. Необходим повторный парсинг.</div> : bombStats.bomb_data_status !== "complete" ? <div className="notice notice--warning">Bomb analytics недоступна: данные неполны или требуют проверки.</div> : <div className="side-stats-grid">{bombStats.teams.map((team) => <article key={`${team.team_id}-${team.team_name}`}><h4>{team.team_name}</h4><p>Plants: {team.plants} / {team.t_rounds_played} · {team.plant_rate === null ? "—" : `${Number(team.plant_rate).toFixed(1)}%`}</p><p>Postplant: {team.postplant_wins}–{team.postplant_losses} · {team.postplant_win_rate === null ? "—" : `${Number(team.postplant_win_rate).toFixed(1)}%`}</p><p>Retake: {team.retake_wins}–{team.retake_losses} · {team.retake_win_rate === null ? "—" : `${Number(team.retake_win_rate).toFixed(1)}%`}</p><p>Explosions: {team.explosions} · Defuses: {team.defuses}</p></article>)}</div>}
            </section>}
            {economyStats && <section className="map-result-card">
              <p className="eyebrow">Экономика и пистолетные раунды</p>
              {economyStats.economy_data_status === "not_parsed" ? <div className="notice notice--warning">Аналитика экономики для этой demo ещё не рассчитана. Необходим повторный парсинг.</div> : economyStats.economy_data_status !== "complete" ? <div className="notice notice--warning">Аналитика экономики неполна: один или несколько раундов не удалось достоверно классифицировать.</div> : <div className="side-stats-grid">{economyStats.teams.map((team) => {
                const row = (label: string, metric: {wins: number; rounds: number; win_rate: string | number | null}) => <p title={metric.win_rate === null ? "Нет выборки" : `${Number(metric.win_rate).toFixed(1)}%`}>{label}: {metric.wins}/{metric.rounds}</p>;
                return <article key={`${team.team_id}-${team.team_name}`}><h4>{team.team_name}</h4>{row("Пистолетные", team.pistol)}{row("Конверсия", team.conversion)}{row("Эко", team.eco)}{row("Форс-бай", team.force_buy)}{row("Полный закуп", team.full_buy)}{row("Анти-эко", team.anti_eco)}{row("Полный закуп против полного", team.full_buy_vs_full_buy)}{row("Камбэк во втором раунде", team.second_round_comeback)}<p>Сохранения: {team.save_data_status === "not_parsed" ? "пока не определяются надёжно" : `${team.save_rounds} раундов, ${team.players_saved} игроков`}</p></article>;
              })}</div>}
            </section>}
            {combatStats && <section className="map-result-card">
              <p className="eyebrow">Combat</p><h3>Opening / Trades / Clutches</h3>
              {combatStats.combat_data_status === "not_parsed" ? <div className="notice notice--warning">Combat analytics ещё не рассчитана. Необходим повторный парсинг.</div> : combatStats.combat_data_status !== "complete" ? <div className="notice notice--warning">Combat analytics неполна или требует проверки.</div> : <><div className="side-stats-grid">{combatStats.teams.map((team) => <article key={`${team.team_id}-${team.team_name}`}><h4>{team.team_name}</h4><p>Opening: {Number(team.opening_kills)}–{Number(team.opening_deaths)}</p><p>Conversion: {team.opening_conversion_rate == null ? "—" : `${Number(team.opening_conversion_rate).toFixed(1)}%`} · Recovery: {team.opening_recovery_rate == null ? "—" : `${Number(team.opening_recovery_rate).toFixed(1)}%`}</p><p>Trade rate: {team.trade_rate == null ? "—" : `${Number(team.trade_rate).toFixed(1)}%`} · Clutches: {Number(team.clutch_wins)}/{Number(team.clutch_opportunities)}</p></article>)}</div><div className="rounds-table">{combatStats.players.map((player) => <div key={`${player.player_id}-${player.nickname}`}><span>{player.nickname}</span><span>Opening {Number(player.opening_kills)}–{Number(player.opening_deaths)}</span><span>Trades {Number(player.trade_kills)}</span><span>Deaths traded {Number(player.deaths_traded)}</span><span>Clutches {Number(player.clutch_wins)}/{Number(player.clutch_opportunities)}</span></div>)}</div></>}
            </section>}
            {utilityStats && <section className="map-result-card"><h3>Utility</h3>
              {utilityStats.utility_data_status === "not_parsed" ? <div className="notice notice--warning">Utility analytics ещё не рассчитана. Необходим повторный парсинг.</div> : utilityStats.utility_data_status !== "complete" ? <div className="notice notice--warning">Utility analytics неполна или требует проверки.</div> : <><div className="side-stats-grid">{utilityStats.teams.map((team) => <article key={`${team.team_id}-${team.team_name}`}><h4>{team.team_name}</h4><p>Utility/round: {team.utility_per_round?.toFixed(2) ?? "—"}</p><p>Damage/round: {team.utility_damage_per_round?.toFixed(2) ?? "—"} · HE {team.he_damage} · Fire {team.fire_damage}</p><p>Enemies flashed: {team.enemies_flashed} · assists {team.flash_assists} · team flashes {team.teammates_flashed}</p></article>)}</div><div className="rounds-table">{utilityStats.players.slice().sort((a,b) => (b.utility_damage_per_round ?? -1) - (a.utility_damage_per_round ?? -1)).slice(0,5).map((player) => <div key={`${player.player_id}-${player.nickname}`}><span>{player.nickname}</span><span>UD/round {player.utility_damage_per_round?.toFixed(2) ?? "—"}</span><span>Utility/round {player.utility_per_round?.toFixed(2) ?? "—"}</span><span>Enemies/flash {player.enemies_flashed_per_flash?.toFixed(2) ?? "—"}</span><span>FA {player.flash_assists}</span></div>)}</div></>}
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
