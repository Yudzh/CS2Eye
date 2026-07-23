# CS2Eye — чистый шаблон

Это новая техническая основа проекта. Старые функции намеренно не перенесены:
их код остаётся в черновой ветке и возвращается только по мере работы над
конкретными законченными слоями.

## Что уже есть

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

- команд и игроков;
- импорта Liquipedia/HLTV/BO3.gg;
- демо-парсинга;
- сравнения команд;
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

## Как начать следующую функцию

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
