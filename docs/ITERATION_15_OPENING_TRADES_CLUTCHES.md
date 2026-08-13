# Итерация 15 — Opening / Trades / Clutches

## Источник и нормализация kills

Используется событие `player_death` demoparser2 0.41.4. Из него читаются `tick`,
`total_rounds_played`, victim (`user_*`), attacker (`attacker_*`), assister
(`assister_*`), `team_num`, `team_clan_name`, `weapon` и `headshot`. Warmup,
technical timeout и `is_game_restart` отбрасываются адаптером.
События `noreplay=true`, которые demoparser2 выдаёт после завершения раунда
(post-defuse/post-round cleanup и финальный world death), также исключаются.

Kill связывается не по ненадёжному parser round counter, а с первым принятым
gameplay `round_end`, tick которого не меньше tick события. Полученный ordinal
связывается с `demo_rounds.round_number`. Строки `demo_kills` заменяются целиком
при reparse. Они содержат player/team snapshots, side, weapon, headshot и флаги
opening/trade/was_traded. Индексы покрывают file+tick, round+tick, player и team
FK, то есть фактические пути чтения и каскадного удаления.

Restart/game-commencing `round_end` не входит в последовательность gameplay
boundaries. `player_death` после последнего gameplay `round_end` относится к
post-match cleanup demoparser2 и отбрасывается; это не повреждение combat data.

## Opening

Opening — самый ранний по tick валидный enemy kill в gameplay round. World
death, suicide, teamkill и событие без обеих достоверных команд пропускаются и
не мешают следующему валидному kill стать opening. У игрока attempt равен
opening kill + opening death. У команды conversion означает победу после своего
opening kill, recovery — победу после своего opening death. CT/T берётся из уже
нормализованного `DemoRound.team_a_side/team_b_side`. Rate при нулевом
denominator равен `null`.

## Trades

`TRADE_WINDOW_SECONDS = 5.0`, tick rate v1 — 64, поэтому точное окно равно 320
ticks. Конфигурация находится в `cs2eye.analytics.combat.config`. Kill B→X —
trade, если в том же раунде X ранее убил teammate B, разница ticks не больше 320,
и оба события — валидные enemy kills. Промежуточные kills не мешают. Исходный
death получает `was_traded` максимум один раз; цепочка A→B→C образует два
независимых trade при соблюдении окна.

В v1 нет надёжных координат/line-of-sight для каждого death. Поэтому team
`eligible_team_deaths` — все валидные enemy deaths, а `trade_rate =
deaths_traded / eligible_team_deaths`. Player temporal opportunity назначается
каждому ещё живому teammate погибшего на момент death. Это прозрачная temporal
аппроксимация, а не утверждение о реальной proximity; её нельзя использовать как
идеальную оценку positioning.

## Clutches и 1vX

В начале раунда alive set строится из участников demo. После каждого валидного
enemy kill victim удаляется. Первая ситуация, где у команды ровно один живой, у
противника один или больше и раунд продолжается, создаёт одну opportunity.
Категория 1vX фиксирует число живых соперников в этот момент (1–5) и больше не
меняется при переходах 1v3→1v2→1v1. Победа определяется нормализованным winner
round, поэтому elimination, bomb explosion и CT defuse обрабатываются одинаково
правильно. Проигрыш последнего игрока — clutch loss. Team winner получает
`clutches_lost_to_opponent` за проигранную соперником clutch opportunity.

Postplant/retake уже доступны на уровне того же round, но точный флаг «clutch
начался после plant» пока не сохраняется: для этого нужен tick bomb_planted в
normalized bomb lifecycle.

## Хранение, статусы и scopes

- `DemoMapResult.combat_data_status`: not_parsed/complete/partial/needs_review/invalid;
- `DemoKill`: нормализованные события и derived flags;
- `DemoPlayerStat.combat_data`: demo+player counters и 1vX breakdown;
- `DemoTeamCombatStat`: demo+team counters;
- `TeamMapAggregate.combat_data`: opening/trade/clutch блок.

Старые demo после migration имеют `not_parsed`, не дают ложных нулей и не входят
в combat aggregates. Partial/needs_review тоже исключены. Team Map использует
существующие all, recent 5/10/20, rank top_15/top_16_30/tier_2_3 и ту же
organization/current-roster snapshot logic. Player detail агрегирует overall,
recent 10, Top-15, Top 16–30 и карты. Scoring Model V2 не изменён.

## API/UI и reparse

`GET /api/v1/demos/{id}/combat-stats` возвращает status, team и player breakdown.
Player detail содержит `combat`; Team Maps и Team Compare получают `combat` в
существующем scope. UI показывает demo breakdown, player opening/trades/clutches,
Team Map compact/expanded показатели и пять combat-метрик сравнения.

Для всех старых demo нужен `replace_existing=true`. Reparse удаляет старые kills
и derived team rows, заменяет player stats и пересчитывает затронутые organization
и roster aggregates. Migration `0019_opening_trades_clutches` поддерживает
downgrade и не удаляет существующие demo.

## Ограничения

Tick rate v1 зафиксирован как 64; если parser начнёт отдавать per-demo tick rate,
его следует сохранить и использовать. Trade proximity/visibility отсутствует.
Clutch postplant/retake start context не определён до нормализации bomb event tick.
Неполный roster или kill без gameplay-round переводит данные в partial/needs_review,
а не в нулевую выборку.
