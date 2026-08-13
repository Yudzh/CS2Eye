# Итерация 12 — Bomb / Postplant / Retake Analytics

## Источник и нормализация

`demoparser2 0.41.4` читает события `bomb_planted`, `bomb_defused` и
`bomb_exploded`. Событие связывается с gameplay-раундом по tick-интервалу между
соседними валидными `round_end`; `total_rounds_played` используется как
дополнительный ключ. Warmup, technical timeout, restart и отброшенные при
нормализации раунды не участвуют.

В `demo_rounds` сохраняются `bomb_planted`, `bomb_defused` и `bomb_exploded`.
Plant считается состоявшимся при событии `bomb_planted`, а также при однозначном
fallback `end_reason=target_bombed|bomb_defused`. Fallback подтверждает именно
plant и не подменяет отсутствующее событие explosion/defuse. Explosion без plant,
defuse без plant, одновременные explosion/defuse и конфликт события с
`end_reason` дают `bomb_data_status=needs_review`.

## Метрики одной demo

`demo_team_bomb_stats` хранит по одной строке на команду карты. Повторный parse
сначала удаляет прежние строки, поэтому операция идемпотентна.

- `plant_rate = bomb_plants / t_rounds_played × 100`;
- postplant opportunity — T поставили bomb;
- postplant win/loss — T выиграли/проиграли такой раунд;
- retake opportunity — команда играла CT, а противник поставил bomb;
- retake win/loss — CT выиграли/проиграли такой раунд;
- postplant/retake win rate используют соответствующее число opportunities.

При нулевом знаменателе rate равен `NULL`, не нулю. Explosions считаются для
T-раундов, defuses — для CT-раундов.

## Агрегаты и выборки

Bomb totals добавлены в существующий `team_map_aggregates` и рассчитываются
`team_map_aggregate_service.py` для `all`, recent 5/10/20, Top 1–15, Top 16–30,
tier 2–3 и внутренних outside/unknown scopes. Обычная статистика карты сохраняет
прежние правила включения. Bomb-часть суммирует только карты со status успешного
parse, полным и согласованным round data и `bomb_data_status=complete`.
Поэтому старая demo не превращается в ложные нули: при отсутствии перепарсенных
карт bomb rate остаётся `NULL`.

Organization использует всю подходящую историю. Current roster использует тот же
`DemoTeamRoster`-фильтр, что и существующая аналитика: `resolution_status=complete`
и точное совпадение `roster_id` с выбранным текущим составом.

## API и UI

`GET /api/v1/demos/{demo_file_id}/bomb-stats` возвращает статус и две командные
строки. `TeamMapScope` содержит объект `bomb` во всех all/recent/versus scopes.
Существующий map comparison возвращает те же три основных rate для обеих команд.

Demo UI показывает plants, postplant, retake, explosions и defuses либо явное
сообщение о необходимости reparse. Team Map отображает основные rates, детали и
значения всех scopes. Team Compare показывает Plant/Postplant/Retake рядом для
обеих команд и сохраняет переключатель organization/current roster.

## Миграция и reparse

Миграция `0017_bomb_postplant_retake` задаёт всем существующим map results
`bomb_data_status=not_parsed`. Старые demo и их прежняя аналитика не удаляются.
Для заполнения bomb analytics нужно выполнить существующий повторный parse:

- кнопка «Повторить парсинг» у demo;
- кнопки «Перепарсить эти демки» / «Перепарсить ВСЕ демки»;
- существующий parse API с `replace_existing=true`.

## Ограничения

Не сохраняются planter, bomb site и plant time. Bomb-метрики не входят в
`map_strength_score`. Economy, pistol, utility, openings, veto, betting и LLM не
реализованы в этой итерации.
