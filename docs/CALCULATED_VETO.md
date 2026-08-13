# Calculated Veto v1

## Actual и Calculated

Actual Veto — сохранённый ordered stream реальных `ban/pick/decider`, введённый
вручную или будущим importer. Calculated Veto — неперсистентный opponent-aware
аналитический расчёт для пары команд. Он не читает и не перезаписывает actual veto.
Scores 0–100 не являются вероятностями.

## Данные и current-roster fallback

Используются существующие `TeamMapAggregate`: Map Strength v2 вместе с confidence,
recent 5/10/20, Top-15/Top 16–30, CT/T, postplant/retake, economy, opening/trade/
clutch и utility. Historical veto даёт pick/ban/first/recent preference. H2H берётся
по карте: current-roster при минимум трёх общих картах, иначе organization.

Organization и current roster смешиваются для каждой карты с
`roster_share = roster_maps / (roster_maps + 5)`. Поэтому две карты не вытесняют
историю организации, а большая roster-выборка постепенно становится основной.
Missing metric отсутствует и его вес перераспределяется — значение не становится 0.

## Формулы

Все суммы используют Scoring V2 factor breakdown, available-weight normalization и
regression к 50 через confidence.

`Matchup Map Score`:

- 35% own Map Strength;
- 25% relative advantage: `clamp(50 + (own strength - opponent strength) × 1.5)`;
- 15% mean recent/current-roster, Top-15 и Top 16–30 performance;
- 10% side matchup: mean `50+(own T-opponent CT)/2` и
  `50+(own CT-opponent T)/2`;
- 5% bomb: postplant против retake соперника и retake против его postplant;
- 5% economy/combat composite;
- 5% relative utility/teamplay composite.

H2H применяется после основной формулы с максимальным весом 8%; его reliability
линейно насыщается к пяти картам. Старый малый H2H не может переломить основу.

`Pick Score`:

- 45% Matchup Map Score;
- 25% relative advantage;
- 20% historical pick preference;
- 10% recent-5 veto preference.

`Ban Score`:

- 40% own weakness (`100 - own strength`);
- 35% opponent Map Strength/threat;
- 15% relative disadvantage (`100 - relative advantage`);
- 10% historical ban/permaban preference.

Veto history reliability: `series / (series + 8)`. Map confidence учитывает Map
Strength confidence, freshness, maps sample, metric coverage и veto sample.

## Simulation и API

`GET /api/v1/analysis/calculated-veto?team_a_id=&team_b_id=&format=bo3`
возвращает model `v1`, map scores/factors/confidence/collision и два сценария, если
first actor неизвестен. При известном `first_actor=team_a|team_b` возвращается один.

Standard BO3 assumption: A ban, B ban, A pick, B pick, A ban, B ban, decider.
Каждый шаг берёт максимальный соответствующий score из оставшегося active pool и
удаляет карту. Rules не объявляются известными: response содержит
`veto_format_assumption=standard_bo3`.

Backtesting groundwork:
`GET /api/v1/analysis/calculated-veto/backtest/{match_id}` возвращает расчёт и
actual ordered veto рядом, не сохраняя и не изменяя их.

## Ограничения v1

Поддержана только deterministic BO3 simulation. Нет calibrated P(pick), P(ban) и
P(map played), seed/coin-toss/tournament rules, динамической game-theory реакции
на оставшийся pool и historical time-travel snapshot для честного production
backtest. Utility сравнивается как общий относительный teamplay signal без
псевдоточного tactical inference.
