from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dev-ui"])

DEV_UI_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>CS2Eye — панель проверки</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <style>
    :root {
      --bg: #0f172a;
      --panel: #111827;
      --panel-2: #1f2937;
      --border: #334155;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --good: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      padding: 24px;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, sans-serif;
    }

    h1, h2, h3 {
      margin-top: 0;
    }

    .layout {
      max-width: 1400px;
      margin: 0 auto;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }

    .full-width {
      margin-top: 20px;
    }

    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 20px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, .2);
    }

    .row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: flex-end;
    }

    label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }

    input {
      width: 220px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--panel-2);
      color: var(--text);
      outline: none;
    }

    input:focus {
      border-color: var(--accent);
    }

    button {
      padding: 10px 14px;
      border: 0;
      border-radius: 10px;
      background: var(--accent);
      color: #00111c;
      cursor: pointer;
      font-weight: 700;
    }

    button:hover {
      opacity: .9;
    }

    .secondary-button {
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
    }

    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .hint {
      color: var(--muted);
      font-size: 13px;
      margin-top: 8px;
    }

    .explain {
      margin-top: 12px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: rgba(255, 255, 255, .03);
    }

    .explain summary {
      cursor: pointer;
      color: var(--accent);
      font-weight: 700;
      font-size: 13px;
    }

    .explain-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin-top: 12px;
      font-size: 13px;
      color: var(--text);
    }

    .explain-item {
      line-height: 1.45;
    }

    .explain-item b {
      color: var(--text);
    }

    .explain-item span {
      color: var(--muted);
    }

    .error {
      padding: 12px;
      border-radius: 10px;
      background: rgba(239, 68, 68, .12);
      border: 1px solid rgba(239, 68, 68, .45);
      color: #fecaca;
      margin-top: 12px;
      white-space: pre-wrap;
    }

    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
      margin-top: 14px;
    }

    .metric {
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
    }

    .metric-title {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }

    .metric-value {
      font-size: 20px;
      font-weight: 700;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 14px;
      overflow: hidden;
      border-radius: 12px;
      font-size: 13px;
    }

    th, td {
      padding: 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }

    th {
      background: var(--panel-2);
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }

    tr:hover td {
      background: rgba(255, 255, 255, .03);
    }

    .pill {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: var(--panel-2);
      border: 1px solid var(--border);
    }

    .pill.good {
      color: #bbf7d0;
      border-color: rgba(34, 197, 94, .5);
      background: rgba(34, 197, 94, .12);
    }

    .pill.warn {
      color: #fde68a;
      border-color: rgba(245, 158, 11, .5);
      background: rgba(245, 158, 11, .12);
    }

    .pill.bad {
      color: #fecaca;
      border-color: rgba(239, 68, 68, .5);
      background: rgba(239, 68, 68, .12);
    }

    .muted {
      color: var(--muted);
    }

    .matchup-card {
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px;
      margin-top: 14px;
    }

    .matchup-title {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }

    .teams {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .team-box {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(0, 0, 0, .15);
    }

    .team-name {
      font-weight: 700;
      margin-bottom: 8px;
    }

    .small-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(80px, 1fr));
      gap: 8px;
      font-size: 13px;
    }

    .details-box {
      margin-top: 14px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--panel-2);
      overflow-x: auto;
    }

    @media (max-width: 1000px) {
      .grid, .teams {
        grid-template-columns: 1fr;
      }

      .summary {
        grid-template-columns: 1fr 1fr;
      }

      input {
        width: 100%;
      }
    }
  </style>
</head>

<body>
  <div class="layout">
    <h1>CS2Eye — панель проверки</h1>

    <p class="muted">
      Минимальная страница для проверки статистики команд, карт, распарсенных матчей и базового прогноза.
    </p>

    <div class="grid">
      <section class="card">
        <h2>Карты команды</h2>

        <div class="row">
          <div>
            <label>Команда</label>
            <input id="teamNameInput" placeholder="Например: Furia">
          </div>

          <div>
            <label>Карта, необязательно</label>
            <input id="teamMapInput" placeholder="Например: mirage">
          </div>

          <button onclick="loadTeamMaps()">Показать</button>
        </div>

        <div class="hint">
          Запрашивает статистику команды по картам.
        </div>

        <details class="explain">
          <summary>Что означают показатели в таблице</summary>

          <div class="explain-grid">
            <div class="explain-item">
              <b>Карта</b> — карта, по которой собрана статистика команды.
            </div>

            <div class="explain-item">
              <b>Команда</b> — команда, для которой считается статистика.
            </div>

            <div class="explain-item">
              <b>Матчи</b> — сколько матчей команды на этой карте есть в базе.
              <span>Чем меньше матчей, тем ниже доверие к выводам.</span>
            </div>

            <div class="explain-item">
              <b>Процент побед</b> — доля побед команды на карте.
              <span>Например, 60% означает 6 побед из 10 матчей.</span>
            </div>

            <div class="explain-item">
              <b>Победы за CT</b> — процент выигранных раундов, когда команда играла за защиту.
            </div>

            <div class="explain-item">
              <b>Победы за T</b> — процент выигранных раундов, когда команда играла за атаку.
            </div>

            <div class="explain-item">
              <b>Установки бомбы</b> — среднее количество установок бомбы командой за карту.
            </div>

            <div class="explain-item">
              <b>Взрывы бомбы</b> — среднее количество раундов за карту, где бомба команды взорвалась.
            </div>

            <div class="explain-item">
              <b>Разминирования</b> — среднее количество разминирований за карту.
            </div>

            <div class="explain-item">
              <b>Сила карты</b> — общий показатель силы команды на карте.
              <span>Сейчас считается из процента побед, свежей формы и размера выборки.</span>
            </div>

            <div class="explain-item">
              <b>Доверие</b> — насколько можно верить статистике.
              <span>Высокая сила карты при низком доверии значит: команда выглядит хорошо, но данных мало.</span>
            </div>

            <div class="explain-item">
              <b>Уровень доверия</b> — текстовая оценка доверия: недостаточно данных, низкое, среднее или высокое.
            </div>

            <div class="explain-item">
              <b>Уровень карты</b> — грубая категория карты: слабая, средняя, сильная и так далее.
            </div>

            <div class="explain-item">
              <b>Последний матч</b> — когда команда последний раз играла эту карту.
              <span>Старая статистика менее надёжна.</span>
            </div>
          </div>
        </details>

        <div id="teamMapsError"></div>
        <div id="teamMapsResult"></div>
      </section>

      <section class="card">
        <h2>Сравнение команд / базовый прогноз</h2>

        <div class="row">
          <div>
            <label>Команда A</label>
            <input id="teamAInput" placeholder="Например: Furia">
          </div>

          <div>
            <label>Команда B</label>
            <input id="teamBInput" placeholder="Например: Fut">
          </div>

          <div>
            <label>Карта, необязательно</label>
            <input id="matchupMapInput" placeholder="Например: mirage">
          </div>

          <button onclick="loadMatchup()">Сравнить</button>
        </div>

        <div class="hint">
          Сравнивает две команды по картам и показывает базовое преимущество.
        </div>

        <details class="explain">
          <summary>Что означает базовый прогноз</summary>

          <div class="explain-grid">
            <div class="explain-item">
              <b>Преимущество</b> — команда, у которой выше показатель силы карты.
            </div>

            <div class="explain-item">
              <b>Разница силы</b> — насколько сильно отличаются команды по карте.
              <span>Чем выше число, тем заметнее преимущество.</span>
            </div>

            <div class="explain-item">
              <b>Доверие к сравнению</b> — насколько надёжно сравнение двух команд.
              <span>Если у одной из команд мало матчей на карте, доверие будет низким.</span>
            </div>

            <div class="explain-item">
              <b>Решение</b> — техническая рекомендация системы:
              нет данных, низкое доверие, нет явного преимущества, небольшое преимущество, преимущество на карте или сильное преимущество.
            </div>

            <div class="explain-item">
              <b>Важно</b> — это ещё не полноценный ИИ-прогноз.
              <span>Сейчас это базовая оценка по статистике карт, CT/T, бомбам, форме и доверию к выборке.</span>
            </div>
          </div>
        </details>

        <div id="matchupError"></div>
        <div id="matchupResult"></div>
      </section>
    </div>

    <section class="card full-width">
      <h2>Распарсенные матчи</h2>

      <div class="row">
        <div>
          <label>Команда, необязательно</label>
          <input id="parseRunsTeamInput" placeholder="Например: Furia">
        </div>

        <div>
          <label>Статус, необязательно</label>
          <input id="parseRunsStatusInput" placeholder="success / failed / running">
        </div>

        <div>
          <label>Лимит</label>
          <input id="parseRunsLimitInput" placeholder="50" value="50">
        </div>

        <button onclick="loadParseRuns()">Показать матчи</button>
      </div>

      <div class="hint">
        Показывает последние распарсенные демки. Через кнопки можно быстро открыть раунды и бомбы.
      </div>

      <details class="explain">
        <summary>Зачем нужен этот блок</summary>

        <div class="explain-grid">
          <div class="explain-item">
            <b>Распарсенные матчи</b> — список запусков парсинга демо.
            <span>Один parse run обычно соответствует одной карте из демки.</span>
          </div>

          <div class="explain-item">
            <b>Статус</b> — результат парсинга: успешно, ошибка или сейчас выполняется.
          </div>

          <div class="explain-item">
            <b>Раунды</b> — открывает сырые round_stats.
            <span>Тут проверяем CT/T, победителя раунда и причину завершения.</span>
          </div>

          <div class="explain-item">
            <b>Бомбы</b> — открывает bomb_round_stats.
            <span>Тут проверяем установки, взрывы и разминирования.</span>
          </div>
        </div>
      </details>

      <div id="parseRunsError"></div>
      <div id="parseRunsResult"></div>
      <div id="parseRunDetails"></div>
    </section>
  </div>

  <script>
    const RU_LABELS = {
      "high": "высокое",
      "medium": "среднее",
      "low": "низкое",
      "not_enough_data": "недостаточно данных",

      "strong": "сильная карта",
      "good": "хорошая карта",
      "average": "средняя карта",
      "weak": "слабая карта",
      "permaban": "почти не играется",

      "success": "успешно",
      "failed": "ошибка",
      "running": "в процессе",

      "planted": "бомба установлена",
      "exploded": "бомба взорвалась",
      "defused": "бомба разминирована",

      "no_bet_low_confidence": "пропуск: низкое доверие",
      "no_clear_advantage": "нет явного преимущества",
      "small_edge": "небольшое преимущество",
      "map_advantage": "преимущество на карте",
      "strong_map_advantage": "сильное преимущество на карте"
    };

    function escapeHtml(value) {
      if (value === null || value === undefined) {
        return "";
      }

      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function translateValue(value) {
      if (value === null || value === undefined || value === "") {
        return "—";
      }

      const normalized = String(value).toLowerCase();

      if (RU_LABELS[normalized]) {
        return RU_LABELS[normalized];
      }

      return value;
    }

    function valueOrDash(value) {
      if (value === null || value === undefined || value === "") {
        return "—";
      }

      return escapeHtml(value);
    }

    function fixed(value, digits = 2) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
      }

      return Number(value).toFixed(digits);
    }

    function pillClass(value) {
      const normalized = String(value || "").toLowerCase();

      if (
        normalized.includes("high") ||
        normalized.includes("strong") ||
        normalized.includes("value") ||
        normalized.includes("advantage") ||
        normalized.includes("success")
      ) {
        return "good";
      }

      if (
        normalized.includes("medium") ||
        normalized.includes("small") ||
        normalized.includes("edge") ||
        normalized.includes("running")
      ) {
        return "warn";
      }

      if (
        normalized.includes("low") ||
        normalized.includes("weak") ||
        normalized.includes("no_bet") ||
        normalized.includes("not_enough") ||
        normalized.includes("permaban") ||
        normalized.includes("failed")
      ) {
        return "bad";
      }

      return "";
    }

    function renderError(containerId, error) {
      const container = document.getElementById(containerId);
      container.innerHTML = `<div class="error">${escapeHtml(error.message || error)}</div>`;
    }

    function clearError(containerId) {
      document.getElementById(containerId).innerHTML = "";
    }

    async function fetchJson(url) {
      const response = await fetch(url);

      let payload = null;

      try {
        payload = await response.json();
      } catch {
        payload = null;
      }

      if (!response.ok) {
        const detail = payload && payload.detail ? payload.detail : response.statusText;
        throw new Error(`${response.status} ${detail}`);
      }

      return payload;
    }

    function buildQuery(params) {
      const searchParams = new URLSearchParams();

      for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined && String(value).trim() !== "") {
          searchParams.set(key, String(value).trim());
        }
      }

      return searchParams.toString();
    }

    async function loadTeamMaps() {
      clearError("teamMapsError");

      const teamName = document.getElementById("teamNameInput").value;
      const mapName = document.getElementById("teamMapInput").value;

      const query = buildQuery({
        team_name: teamName,
        map_name: mapName,
      });

      const url = `/api/v1/demos/analysis/team-maps${query ? "?" + query : ""}`;

      try {
        const payload = await fetchJson(url);
        renderTeamMaps(payload);
      } catch (error) {
        document.getElementById("teamMapsResult").innerHTML = "";
        renderError("teamMapsError", error);
      }
    }

    function renderTeamMaps(payload) {
      const items = payload.items || [];

      const totalMatches = items.reduce(
        (sum, item) => sum + Number(item.total_matches_on_map || 0),
        0
      );

      const bestItem = [...items].sort(
        (a, b) => Number(b.map_strength_score || 0) - Number(a.map_strength_score || 0)
      )[0];

      const summaryHtml = `
        <div class="summary">
          <div class="metric">
            <div class="metric-title">Команда</div>
            <div class="metric-value">${valueOrDash(payload.team_name || "все")}</div>
          </div>

          <div class="metric">
            <div class="metric-title">Карт найдено</div>
            <div class="metric-value">${items.length}</div>
          </div>

          <div class="metric">
            <div class="metric-title">Матчей в выборке</div>
            <div class="metric-value">${totalMatches}</div>
          </div>

          <div class="metric">
            <div class="metric-title">Лучшая карта</div>
            <div class="metric-value">${bestItem ? valueOrDash(bestItem.map_name) : "—"}</div>
          </div>
        </div>
      `;

      const rowsHtml = items.map(item => `
        <tr>
          <td><b>${valueOrDash(item.map_name)}</b></td>
          <td>${valueOrDash(item.team_name)}</td>
          <td>${item.total_matches_on_map}</td>
          <td>${fixed(item.win_rate_on_map)}%</td>
          <td>${fixed(item.ct_win_rate)}%</td>
          <td>${fixed(item.t_win_rate)}%</td>
          <td>${fixed(item.avg_bomb_plants_per_map)}</td>
          <td>${fixed(item.avg_bomb_explosions_per_map)}</td>
          <td>${fixed(item.avg_bomb_defuses_per_map)}</td>
          <td><b>${fixed(item.map_strength_score)}</b></td>
          <td>${fixed(item.map_confidence_score)}</td>
          <td>
            <span class="pill ${pillClass(item.map_confidence_level)}">
              ${valueOrDash(translateValue(item.map_confidence_level))}
            </span>
          </td>
          <td>
            <span class="pill ${pillClass(item.map_tier)}">
              ${valueOrDash(translateValue(item.map_tier))}
            </span>
          </td>
          <td>${valueOrDash(item.last_played_date_on_map)}</td>
        </tr>
      `).join("");

      const tableHtml = `
        <table>
          <thead>
            <tr>
              <th>Карта</th>
              <th>Команда</th>
              <th>Матчи</th>
              <th>Победы</th>
              <th>Победы за CT</th>
              <th>Победы за T</th>
              <th>Установки бомбы</th>
              <th>Взрывы бомбы</th>
              <th>Разминирования</th>
              <th>Сила карты</th>
              <th>Доверие</th>
              <th>Уровень доверия</th>
              <th>Уровень карты</th>
              <th>Последний матч</th>
            </tr>
          </thead>

          <tbody>
            ${rowsHtml || `<tr><td colspan="14" class="muted">Нет данных</td></tr>`}
          </tbody>
        </table>
      `;

      document.getElementById("teamMapsResult").innerHTML = summaryHtml + tableHtml;
    }

    async function loadMatchup() {
      clearError("matchupError");

      const teamAName = document.getElementById("teamAInput").value;
      const teamBName = document.getElementById("teamBInput").value;
      const mapName = document.getElementById("matchupMapInput").value;

      const query = buildQuery({
        team_a_name: teamAName,
        team_b_name: teamBName,
        map_name: mapName,
      });

      const url = `/api/v1/demos/analysis/matchup${query ? "?" + query : ""}`;

      try {
        const payload = await fetchJson(url);
        renderMatchup(payload);
      } catch (error) {
        document.getElementById("matchupResult").innerHTML = "";
        renderError("matchupError", error);
      }
    }

    function renderTeamBox(team) {
      return `
        <div class="team-box">
          <div class="team-name">${valueOrDash(team.team_name)}</div>

          <div class="small-grid">
            <div>
              <span class="muted">Матчи:</span>
              <b>${team.total_matches_on_map}</b>
            </div>

            <div>
              <span class="muted">Победы:</span>
              <b>${fixed(team.win_rate_on_map)}%</b>
            </div>

            <div>
              <span class="muted">За CT:</span>
              <b>${fixed(team.ct_win_rate)}%</b>
            </div>

            <div>
              <span class="muted">За T:</span>
              <b>${fixed(team.t_win_rate)}%</b>
            </div>

            <div>
              <span class="muted">Сила карты:</span>
              <b>${fixed(team.map_strength_score)}</b>
            </div>

            <div>
              <span class="muted">Доверие:</span>
              <b>${fixed(team.map_confidence_score)}</b>
            </div>

            <div>
              <span class="muted">Уровень карты:</span>
              <span class="pill ${pillClass(team.map_tier)}">
                ${valueOrDash(translateValue(team.map_tier))}
              </span>
            </div>

            <div>
              <span class="muted">Уровень доверия:</span>
              <span class="pill ${pillClass(team.map_confidence_level)}">
                ${valueOrDash(translateValue(team.map_confidence_level))}
              </span>
            </div>
          </div>
        </div>
      `;
    }

    function renderMatchup(payload) {
      const items = payload.items || [];

      const cardsHtml = items.map(item => `
        <div class="matchup-card">
          <div class="matchup-title">
            <h3>${valueOrDash(item.map_name)}</h3>

            <div>
              <span class="pill ${pillClass(item.matchup_confidence_level)}">
                ${valueOrDash(translateValue(item.matchup_confidence_level))}
              </span>

              <span class="pill ${pillClass(item.recommendation)}">
                ${valueOrDash(translateValue(item.recommendation))}
              </span>
            </div>
          </div>

          <div class="summary">
            <div class="metric">
              <div class="metric-title">Преимущество</div>
              <div class="metric-value">${valueOrDash(item.advantage_team_name)}</div>
            </div>

            <div class="metric">
              <div class="metric-title">Разница силы</div>
              <div class="metric-value">${fixed(item.advantage_score)}</div>
            </div>

            <div class="metric">
              <div class="metric-title">Доверие к сравнению</div>
              <div class="metric-value">${valueOrDash(translateValue(item.matchup_confidence_level))}</div>
            </div>

            <div class="metric">
              <div class="metric-title">Решение</div>
              <div class="metric-value">${valueOrDash(translateValue(item.recommendation))}</div>
            </div>
          </div>

          <div class="teams">
            ${renderTeamBox(item.team_a)}
            ${renderTeamBox(item.team_b)}
          </div>
        </div>
      `).join("");

      document.getElementById("matchupResult").innerHTML = cardsHtml || `
        <div class="hint">Нет данных для сравнения</div>
      `;
    }

    async function loadParseRuns() {
      clearError("parseRunsError");

      document.getElementById("parseRunDetails").innerHTML = "";

      const teamName = document.getElementById("parseRunsTeamInput").value;
      const statusFilter = document.getElementById("parseRunsStatusInput").value;
      const limit = document.getElementById("parseRunsLimitInput").value || "50";

      const query = buildQuery({
        team_name: teamName,
        status_filter: statusFilter,
        limit: limit,
      });

      const url = `/api/v1/demos/parse-runs${query ? "?" + query : ""}`;

      try {
        const payload = await fetchJson(url);
        renderParseRuns(payload);
      } catch (error) {
        document.getElementById("parseRunsResult").innerHTML = "";
        renderError("parseRunsError", error);
      }
    }

    function renderParseRuns(payload) {
      const items = payload.items || [];

      const rowsHtml = items.map(item => `
        <tr>
          <td>${valueOrDash(item.match_date)}</td>
          <td>${valueOrDash(item.tournament_name)}</td>
          <td>
            <b>${valueOrDash(item.team_a_name)}</b>
            <span class="muted">vs</span>
            <b>${valueOrDash(item.team_b_name)}</b>
          </td>
          <td>${valueOrDash(item.map_name)}</td>
          <td>${valueOrDash(item.map_number)}</td>
          <td>${valueOrDash(item.rounds_count)}</td>
          <td>
            <span class="pill ${pillClass(item.status)}">
              ${valueOrDash(translateValue(item.status))}
            </span>
          </td>
          <td>${valueOrDash(item.demo_file_name)}</td>
          <td>
            <div class="actions">
              <button class="secondary-button" onclick="loadParseRunRounds('${item.id}')">
                Раунды
              </button>

              <button class="secondary-button" onclick="loadParseRunBombs('${item.id}')">
                Бомбы
              </button>
            </div>
          </td>
        </tr>
      `).join("");

      const tableHtml = `
        <table>
          <thead>
            <tr>
              <th>Дата</th>
              <th>Турнир</th>
              <th>Матч</th>
              <th>Карта</th>
              <th>№ карты</th>
              <th>Раунды</th>
              <th>Статус</th>
              <th>Файл</th>
              <th>Действия</th>
            </tr>
          </thead>

          <tbody>
            ${rowsHtml || `<tr><td colspan="9" class="muted">Нет данных</td></tr>`}
          </tbody>
        </table>
      `;

      document.getElementById("parseRunsResult").innerHTML = tableHtml;
    }

    async function loadParseRunRounds(parseRunId) {
      clearError("parseRunsError");

      const url = `/api/v1/demos/parse-runs/${parseRunId}/rounds`;

      try {
        const payload = await fetchJson(url);
        renderParseRunRounds(payload);
      } catch (error) {
        document.getElementById("parseRunDetails").innerHTML = "";
        renderError("parseRunsError", error);
      }
    }

    function renderParseRunRounds(payload) {
      const items = payload.items || [];

      const rowsHtml = items.map(item => `
        <tr>
          <td>${item.round_number}</td>
          <td>${valueOrDash(item.ct_team_name)}</td>
          <td>${valueOrDash(item.t_team_name)}</td>
          <td>${valueOrDash(item.winner_team_name)}</td>
          <td>${valueOrDash(item.winner_side)}</td>
          <td>${valueOrDash(item.reason)}</td>
        </tr>
      `).join("");

      document.getElementById("parseRunDetails").innerHTML = `
        <div class="details-box">
          <h3>Раунды parse run: ${valueOrDash(payload.parse_run_id)}</h3>

          <table>
            <thead>
              <tr>
                <th>Раунд</th>
                <th>CT команда</th>
                <th>T команда</th>
                <th>Победитель</th>
                <th>Сторона победителя</th>
                <th>Причина</th>
              </tr>
            </thead>

            <tbody>
              ${rowsHtml || `<tr><td colspan="6" class="muted">Нет данных по раундам</td></tr>`}
            </tbody>
          </table>
        </div>
      `;
    }

    async function loadParseRunBombs(parseRunId) {
      clearError("parseRunsError");

      const url = `/api/v1/demos/parse-runs/${parseRunId}/bomb-rounds`;

      try {
        const payload = await fetchJson(url);
        renderParseRunBombs(payload);
      } catch (error) {
        document.getElementById("parseRunDetails").innerHTML = "";
        renderError("parseRunsError", error);
      }
    }

    function renderParseRunBombs(payload) {
      const items = payload.items || [];

      const rowsHtml = items.map(item => `
        <tr>
          <td>${item.round_number}</td>
          <td>${valueOrDash(item.planter_name)}</td>
          <td>${valueOrDash(item.planter_team_name)}</td>
          <td>${valueOrDash(item.defuser_name)}</td>
          <td>${valueOrDash(item.defuser_team_name)}</td>
          <td>
            <span class="pill ${pillClass(item.outcome)}">
              ${valueOrDash(translateValue(item.outcome))}
            </span>
          </td>
          <td>${valueOrDash(item.plant_tick)}</td>
          <td>${valueOrDash(item.defuse_tick)}</td>
          <td>${valueOrDash(item.explosion_tick)}</td>
        </tr>
      `).join("");

      document.getElementById("parseRunDetails").innerHTML = `
        <div class="details-box">
          <h3>Бомбы parse run: ${valueOrDash(payload.parse_run_id)}</h3>

          <table>
            <thead>
              <tr>
                <th>Раунд</th>
                <th>Кто поставил</th>
                <th>Команда planter</th>
                <th>Кто разминировал</th>
                <th>Команда defuser</th>
                <th>Итог</th>
                <th>Plant tick</th>
                <th>Defuse tick</th>
                <th>Explosion tick</th>
              </tr>
            </thead>

            <tbody>
              ${rowsHtml || `<tr><td colspan="9" class="muted">Нет данных по бомбам</td></tr>`}
            </tbody>
          </table>
        </div>
      `;
    }
  </script>
</body>
</html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def get_dev_ui() -> HTMLResponse:
    return HTMLResponse(content=DEV_UI_HTML)