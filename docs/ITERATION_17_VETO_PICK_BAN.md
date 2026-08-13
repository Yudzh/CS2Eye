# Итерация 17 — Veto / Pick / Ban Analytics

## Источник и модель

В текущем проекте veto не сохранялся ни в metadata демки, ни в `Match`. Надёжного
используемого импортера BO3.gg veto также нет. Поэтому v1 является manual-first:
admin редактор серии пишет `match_veto_actions`, а `VetoService.replace` служит
идемпотентной точкой интеграции будущего разрешённого importer. HLTV scraping не
используется. Automatic import в этой итерации не включён.

`MatchVetoAction` хранит series, обязательный уникальный `order_index`, team
snapshot, `ban|pick|decider`, нормализованное имя карты, source/external id и
source timestamp. `Match.veto_data_status` различает `not_available`, `complete`,
`partial`, `needs_review`, `invalid`; существующие серии получают
`not_available`. BO1/BO3/BO5 используют один ordered event stream: схема действий
не выводится из формата и никогда не генерируется при неизвестном порядке.

Сыгранная `DemoFile` получает `map_role` и `picked_by_team_id`. Pick команды даёт
для неё own pick, для второй стороны — opponent pick; neutral action даёт decider.
Отсутствие точной связи остаётся `unknown`.

## Rates, scopes и performance

Denominator v1 для pick/ban/first rates — число серий выбранного scope со статусом
`complete|partial`, где карта входит в указанную для серии `map_pool_version`.
Если версия неизвестна или справочник ещё пуст, eligible считается каждая серия с
валидным veto. Нулевой denominator даёт `null`, а не 0.

First ban — ban карты с минимальным `order_index` среди действий этой команды в
серии. First pick аналогично использует первый `pick` этой команды, а не первое её
действие. Own/opponent pick WR определяется владельцем pick action и фактическим
победителем связанной Demo map. Decider WR использует neutral `decider`.

Поддержаны organization/current_roster, recent 5/10/20, существующие opponent rank
group keys и tournament context LAN/online/stage/playoff/elimination. Current roster
принимает серию только при exact current `roster_id` и `resolution_status=complete`
на каждой её demo map — используется та же политика, что в Match Series.

## Map pool, derived signals и confidence

`map_pool_entries` — компактный versioned справочник с периодом и active flag;
`Match.map_pool_version` связывает историческую серию с версией. Inactive история
сохраняется и показывается, но UI исключает её из текущих preferred-map signals.

Permaban confidence объединяет first-ban frequency (65%), overall ban rate (35%),
sample saturation при 8 сериях и exponential freshness; likely требует минимум 5
серий и score 60. Pick preference аналогично использует pick rate (65%), first-pick
rate (35%) и freshness, но никогда winrate. Veto confidence отдельно учитывает
sample 45%, freshness 30%, completeness 25%; это не strength modifier.

Compare возвращает historical pick-vs-ban collision и deterministic availability
(`likely_available|contested|likely_removed|unknown`). H2H — отдельный профиль
последних трёх очных серий и не смешивается с organization aggregate. Ни один
label не является predicted/expected veto.

## API и UI

- `GET /api/v1/analysis/teams/{id}/veto` — scopes, sample, confidence, map profile;
- `GET /api/v1/analysis/compare/teams/{a}/{b}/veto` — две стороны, collisions,
  availability и отдельный H2H;
- `GET /api/v1/matches/{id}` — ordered veto/status и роли карт;
- `PUT /api/v1/matches/{id}/veto` — replace/add/edit/reorder/delete/complete.

Team Page показывает Map Veto Profile и compact performance, Team Compare — veto
таблицу, collision/availability, Match detail — порядок и status. Admin list имеет
редактор строк в формате `1. Spirit removed Inferno`, `Spirit picked Dust2`,
`Cache was left over`; нумерация необязательна. Команда сверяется с участниками
серии без учёта регистра, карта — с нормализованным справочником и, если указана
версия, pool серии. Удаление action выполняется удалением строки перед сохранением.

## Validation и ограничения

Проверяются duplicate order/map, ban→pick той же карты, unknown team/action,
несколько decider, action после decider, unknown/out-of-pool map. Невалидный stream
нельзя отметить complete. Unknown/out-of-pool получает review, структурные ошибки
— invalid. Полнота конкретных tournament veto-протоколов не угадывается.

Нет automatic external import, вероятностей и Expected Veto. Match/Player/Team/Map
Strength и Scoring Model не изменены. Историческая eligibility максимально точна
только у серий с заполненным `map_pool_version`.
