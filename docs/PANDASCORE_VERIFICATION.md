# Проверка PandaScore

Реальный бесплатный доступ проверен 26 октября 2026 года токеном из локальной
серверной конфигурации. Значение токена не включено в файлы или отчёт.

Запрос: `GET /csgo/matches/past`, Bearer-заголовок,
`range[begin_at]=2026-10-24T00:00:00Z,2026-10-25T00:00:00Z`,
`sort=begin_at`, `per_page=100`, `page=1`. Получен HTTP 200,
`X-Rate-Limit-Remaining: 999`. В диапазоне 49 матчей, следующая страница
не требовалась. G2 — Natus Vincere найден в ответе PandaScore:

| Поле | Значение |
| --- | --- |
| Match ID | 1752691 |
| Начало | 2026-10-24T16:22:51Z |
| Статус | finished |
| G2 ID / счёт | 3210 / 0 |
| NAVI ID / счёт | 3216 / 2 |
| winner_id | 3216 |
| number_of_games | 3 |
| forfeit | false |
| League | PGL Masters, ID 5442 |
| Series | Bucharest 2026, ID 11118 |
| Tournament | Group Stage, ID 22222 |

Затем новый сервис синхронизации дважды проверен на реальном API с изолированной
SQLite БД в памяти. Первый запуск выполнил поиск по дате, сопоставил событие и
команды и сохранил результат 0:2 с `source=pandascore`, статусом `confirmed` и
внешним ID 1752691. Прогнозы не создавались. Второй запуск использовал бесплатный
список с `filter[id]=1752691`, подтвердил тот же результат и не добавил
повторных записей аудита. Отдельный `/csgo/matches/{id}` не вызывался.
Результат не подменялся заранее известным результатом BO3.

Источники документации:

- [Авторизация](https://developers.pandascore.co/docs/authentication)
- [Планы и доступность endpoints](https://developers.pandascore.co/docs/plan-reference)
- [Лимиты](https://developers.pandascore.co/docs/rate-and-connections-limits)
- [Список завершённых матчей](https://developers.pandascore.co/reference/get_csgo_matches_past-1)

Проверка не является проверкой production: на VPS ещё нужно настроить токен,
доставить ветку `telegtam-prod` обычным `cs2eye-deploy` и проверить реальный
пользовательский поток — турнир, сохранённый прогноз, проверку результата,
историю и административное исправление. Проверка схемы выполнена тестом миграции
на изолированной SQLite; PostgreSQL-блокировку и применение миграции необходимо
проверить при доставке на VPS. Контейнеры и production Telegram polling в ходе
этой работы не запускались.
