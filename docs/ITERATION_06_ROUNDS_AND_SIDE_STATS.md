# Итерация 06: раунды и статистика CT/T

## Хранение

`demo_rounds` содержит один завершённый игровой раунд. Уникальность
`(demo_file_id, round_number)` не допускает дублей, удаление demo каскадно удаляет
раунды. `demo_team_side_stats` содержит две агрегированные строки на карту — по одной
на raw-команду результата. `demo_map_results.round_data_status` принимает
`not_parsed`, `complete`, `partial`, `needs_review`, `invalid`.

## Извлечение и нормализация

Источник — `round_end` и состояние команд в соответствующем tick. Warmup,
restart/game commencing и повтор raw-номера пропускаются. Пользовательская нумерация
строится заново с 1. Названия сторон сопоставляются только с `team_a/team_b` уже
сохранённого результата карты через общий нормализатор имён; fuzzy matching нет.

Для MR12 fallback относит 1–12 к первой половине, 13–24 ко второй, последующие
раунды — к overtime с шестираундовыми OT-периодами. Фактические clan names на каждом
tick определяют CT/T, поэтому halftime и OT side switch не выводятся из текущего
состава игроков.

Причина завершения централизованно приводится к `target_bombed`, `bomb_defused`,
`terrorists_eliminated`, `cts_eliminated`, `target_saved`, `hostages_rescued`,
`terrorists_escaped`, `game_commencing`, `draw` или `unknown`.

Счёт до/после строится последовательным добавлением победы определённой команде.
Raw-score используется для диагностики. После нормализации число валидных раундов и
победы обеих команд сверяются с `demo_map_results`; расхождение даёт
`needs_review`, не удаляя player stats.

## CT/T агрегаты

Агрегаты пересчитываются только из сохранённых `demo_rounds`:

`win_rate = rounds_won / rounds_played * 100`.

При нулевой выборке rate равен `NULL`. CT/T включает overtime; first/second half —
только regulation. Значения хранятся с четырьмя знаками, UI показывает один.

## API и UI

- `GET /api/v1/demos/{id}/rounds` — фильтры `phase`, `half`, `winner_side`,
  пагинация `page/page_size`.
- `GET /api/v1/demos/{id}/side-stats` — две команды и CT/T/half/OT/total.
- `POST /api/v1/demos/{id}/recalculate-side-stats` — пересчёт из БД без `.dem`.
- map-result включает статус и parsed/expected counts.

UI показывает CT/T карточки, проценты, половины, OT, раскрываемую таблицу раундов и
фильтры regulation/overtime/CT/T.

## Повторный parsing и ограничения

`replace_existing=true` заменяет map result, rounds, side stats и player stats в
одной транзакции. Замена файла каскадно инвалидирует раундовые данные. Экономика,
buy types, post-plant, retake, pistol/opening/trade/clutch/utility и многокарточные
агрегаты не рассчитываются.
