# CS2Eye

Это новая техническая основа проекта. Старые функции намеренно не перенесены:
их код остаётся в черновой ветке и возвращается только по мере работы над
конкретными законченными слоями.

## Готовый продуктовый слой

Итерация 01: получение Valve World top-40 из BO3.gg с активной
витриной top-30.

- безопасная проверка источника без изменения БД;
- ручное обновление top-40;
- активны и видимы ровно команды текущего top-30;
- команды на местах 31–40 хранятся как теневые: для них обновляются
  рейтинг, составы и статистика, но они не показываются в витрине;
- выбывшие команды сохраняются, но деактивируются;
- история запусков и рейтинговые снимки;
- исходные ответы для диагностики;
- API и интерфейс со списком команд;
- защита от неполного или противоречивого ответа.

Контракт итерации:
[`docs/ITERATION_01_TOP_TEAMS.md`](docs/ITERATION_01_TOP_TEAMS.md).

Итерация 02: актуальные игроки и тренеры Top-30 с историей составов.

- один запрос деталей для каждой активной команды только к BO3.gg;
- пять игроков и доступные тренеры;
- идемпотентная синхронизация без удаления истории;
- актуальный состав и дата синхронизации в API и UI.

Контракт итерации:
[`docs/ITERATION_02_TEAM_ROSTERS.md`](docs/ITERATION_02_TEAM_ROSTERS.md).

Итерация 05: сравнение двух активных команд текущего Top-30.

- рейтинг, очки и активные составы из БД;
- переиспользование расчёта силы итерации 04;
- относительная сила выбранной пары без трактовки как вероятности;
- сравнение игроков по ролям и детерминированный итог;
- восстановление выбранных команд из URL `/compare?team_a=…&team_b=…`.

Контракт итерации:
[`docs/ITERATION_05_TEAM_COMPARISON.md`](docs/ITERATION_05_TEAM_COMPARISON.md).

## Инфраструктура

- FastAPI;
- PostgreSQL 16;
- SQLAlchemy Async;
- Alembic и начальная baseline-миграция;
- React + TypeScript + Vite;
- Docker Compose для локальной разработки;
- pgAdmin;
- liveness/readiness endpoints;
- минимальный UI, проверяющий API и БД;
- базовый backend-тест.

## Чего здесь намеренно нет

- подробного импорта команд и игроков;
- демо-парсинга;
- карт, матчей и head-to-head в сравнении команд;
- betting draft и прогнозов;
- рыночной аналитики;
- незавершённых страниц и API старого проекта.

## Первый запуск

```bash
cp .env.example .env
docker compose -f compose.local.yml up --build
```

После запуска:

- UI: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>
- API liveness: <http://localhost:8000/api/v1/health/live>
- API + DB readiness: <http://localhost:8000/api/v1/health/ready>
- pgAdmin: <http://localhost:5050>

Остановка:

```bash
docker compose -f compose.local.yml down
```

Полный сброс локальных данных:

```bash
docker compose -f compose.local.yml down -v
```

## Локальные проверки

Backend:

```bash
poetry install
poetry run pytest
```

Frontend:

```bash
cd webui
npm ci
npm run build
```

Compose:

```bash
docker compose -f compose.local.yml config
```

## Как начать следующую итерацию

Перед кодом заполнить короткий контракт:

```text
Сценарий:
Пользователь может ...

Вход:
...

Результат:
...

Ошибки и пустые состояния:
...

Definition of Done:
БД + API + UI + тесты + Docker-проверка.
```

Подробные ограничения находятся в
[`docs/DEVELOPMENT_RULES.md`](docs/DEVELOPMENT_RULES.md).

Пошаговая замена текущего локального проекта без удаления `.git` описана в
[`docs/LOCAL_REPLACEMENT.md`](docs/LOCAL_REPLACEMENT.md).
