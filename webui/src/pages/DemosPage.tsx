import { FormEvent, useEffect, useState } from "react";

import { getDemoFiles, getDemoPlayerStats, getDemoTournaments, parseDemoFile, parseDemoFiles, uploadDemoFiles } from "../api";
import type { DemoListResponse, DemoParseResponse, DemoPlayerStatsResponse, DemoTournamentOption, DemoUploadResponse, DemoUploadStatus } from "../types";


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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} КБ`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} МБ`;
  return `${(bytes / 1024 ** 3).toFixed(2)} ГБ`;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Не удалось выполнить запрос.";
}

export function DemosPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [tournament, setTournament] = useState("");
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

  useEffect(() => {
    void getDemoTournaments().then(setTournaments).catch((error) => setListError(message(error)));
  }, []);

  async function submitUpload(event: FormEvent) {
    event.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      setUploadResult(await uploadDemoFiles(tournament, matchDate, files));
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
          {listResult && <div className="demo-list"><div className="demo-parse-actions"><h3>{listResult.tournament_name} · {listResult.year}</h3><button className="button button--primary" disabled={parsingMode !== null || listResult.total_files === 0} onClick={() => void parseAll()}>{parsingMode === "new" ? "Парсинг…" : "Распарсить рейтинг игроков"}</button><button className="button" disabled={parsingMode !== null || listResult.total_files === 0} onClick={() => void parseAll(true)}>{parsingMode === "all" ? "Повторный парсинг…" : "Перепарсить все демки"}</button></div>{parseResult && <><div className="parse-summary"><span>Обработано: {parseResult.parsed_count}</span><span>Пропущено: {parseResult.skipped_count}</span><span>Ошибок: {parseResult.failed_count}</span><span>Найдено игроков: {parseResult.files.reduce((sum, file) => sum + file.players_found, 0)}</span><span>Связано: {parseResult.files.reduce((sum, file) => sum + file.players_linked, 0)}</span><span>Не связано: {parseResult.files.reduce((sum, file) => sum + file.players_unlinked, 0)}</span></div>{parseResult.files.flatMap((file) => file.diagnostics).map((diagnostic, index) => <div className="notice notice--warning" key={`${diagnostic}-${index}`}>{diagnostic}</div>)}{parseResult.files.flatMap((file) => file.unlinked_players).length > 0 && <div className="unlinked-players"><strong>Нераспознанные игроки</strong>{parseResult.files.flatMap((file) => file.unlinked_players).map((player, index) => <span key={`${player.demo_filename}-${player.steam_id}-${index}`}>{player.nickname} · {player.steam_id || "Steam ID нет"} · {player.team_name || "команда не указана"} · {player.demo_filename}</span>)}</div>}</>}{playerStats && <div className="opponent-classification"><strong>{playerStats.filename}</strong><div className="opponent-classification__head"><span>Игрок</span><span>Команда игрока</span><span>Соперник</span><span>Место</span><span>Группа</span></div>{playerStats.players.map((player, index) => <div key={`${player.steam_id}-${index}`}><span>{player.nickname}</span><span>{player.demo_team_name || "—"}</span><span>{player.opponent_team_name || "—"}</span><span>{player.opponent_rank ?? "—"}</span><span>{opponentGroupLabels[player.opponent_rank_group]}</span></div>)}</div>}{listResult.dates.length === 0 ? <div className="empty-state">Демок не найдено.</div> : listResult.dates.map((group) => <section key={group.match_date}><h4>{new Intl.DateTimeFormat("ru-RU", { dateStyle: "long", timeZone: "UTC" }).format(new Date(`${group.match_date}T00:00:00Z`))}</h4>{group.files.map((file) => <div className="stored-demo" key={file.id}><strong>{file.filename}</strong><span>{formatSize(file.file_size_bytes)} · {parseStatusLabels[file.parse_status]}</span><div className="stored-demo__action"><code>{file.sha256.slice(0, 12)}…</code>{file.parse_status === "success" && <button className="button" disabled={parsingFileId === file.id} onClick={() => void showPlayerStats(file.id)}>Почему группа?</button>}<button className="button" disabled={parsingFileId === file.id} onClick={() => void parseOne(file.id, file.parse_status === "success")}>{parsingFileId === file.id ? "Парсинг…" : file.parse_status === "success" ? "Повторить парсинг" : "Распарсить"}</button></div></div>)}</section>)}</div>}
        </section>
      </div>
    </main>
  );
}
