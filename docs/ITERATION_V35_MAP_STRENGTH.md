# ИТЕРАЦИЯ V3.5 — Map Strength V3

Реализован отдельный слой `map_strength.v3`, calculation revision `v3.5.1`.
Проверка локальных реальных данных: 2026-09-05. Legacy сохранён. Matchup V3 не изменён и не начат.

## Файлы

Backend:
- `src/cs2eye/analytics/map_strength_v3_config.py`: формулы, пороги, применимость составов.
- `src/cs2eye/services/map_strength_v3_service.py`: наблюдения, компоненты, профиль, temporal filtering, reliability, snapshot, sanity audit.
- `src/cs2eye/services/effective_roster_service.py`: необязательные `permanent_player_ids` и `known_before`; обычные вызовы сохраняют прежнее поведение.
- `src/cs2eye/api/routers/analysis.py`: pool, отдельная карта, recalculate, event context.
- `src/cs2eye/models/team.py`: nullable Map V3 score/delta.

Frontend:
- `webui/src/components/MapsV3.tsx`: карточки, страница карты, CT/T, компоненты, diagnostic profile.
- `webui/src/App.tsx`: подключение блока и маршрута `/teams/{id}/maps/{map}`.
- `webui/src/api.ts`, `webui/src/types.ts`, `webui/src/styles.css`.

Migration: `alembic/versions/0052_map_strength_v35_nullable.py`, revision `0052_map_strength_v35_nullable`, parent `0051_roster_factor`; применена к локальной PostgreSQL.
Контекст, map entity ID, статус, компоненты и reliability breakdown сохраняются в JSON breakdown существующего V3 snapshot. Legacy-таблицы не меняются. GET считает on demand без использования старых V3 snapshots; POST recalculate сохраняет стандартный текущий контекст. Historical/event requests не перезаписывают стандартный snapshot.

## Формулы

### Map Strength

`round(0.45 × Results Quality + 0.25 × Side Performance + 0.30 × Map Execution, 2)`.
Если компонент недоступен, его вес исключается, доступные веса делятся на их сумму.
Отсутствие всех применимых карт: `score=null`, `reliability=0`, `status=NOT_ENOUGH_DATA`.

`delta_vs_team = round(map_score − team_strength_v3, 2)` — без clipping и масштабирования.
Team Strength читается только после расчёта Map score и используется исключительно для delta/status.
Для текущего и historical контекстов вызывается существующий TeamStrengthV3Service с проверкой calculation revision. Расчёт baseline выполняется в отдельной rollback-сессии: устаревший JSON не используется напрямую, изменения Team Strength не сохраняются из Map Strength. Event stand-in penalty не добавляется к Map score.

Статусы: delta ≥8 VERY_STRONG; ≥3 STRONG; ≤−8 VERY_WEAK; ≤−3 WEAK; иначе NEUTRAL.
Отсутствующий Team baseline: BASELINE_UNAVAILABLE. Reliability <40: дополнительный флаг LOW_SAMPLE.

### Results Quality

Переиспользована `adjusted_map_quality` из OpponentAdjustedResultsService, без изменений Team Strength:

```
s = clamp((61 − min(rank, 60)) / 60, 0, 1)
c = s, если historical rank известен; иначе 0.5
result = 0.62 + 0.38c для победы; 0.38c для поражения
margin = clamp(round_diff / 13, −1, 1)
margin_value = clamp(0.5 + 0.30margin + 0.20(c − 0.5), 0, 1)
observation_score = round(100 × (0.70result + 0.30margin_value), 2)
RQ = round(sum(observation_score × observation_weight) / sum(observation_weight), 2)
```

Берётся последний ranking snapshot с `ranking_date <= event_date`; сегодняшнего fallback нет.
Unknown rank явно отражается в breakdown и снижает reliability. `c=0.5` — неизвестный контекст соперника, не подставленный Map score.
Top 1–10, 11–20, 21–30, Others, Unknown используются только в breakdown; повторных весов ranking groups нет.

### CT / T

CT = 35% round winrate + 20% opening success + 15% economy + 15% retake + 15% conversion/recovery.

T = 30% round winrate + 20% T opening success + 15% economy + 20% postplant + 15% conversion/recovery.

Каждая rate = `100 × weighted wins / weighted opportunities`.
Conversion/recovery = 50% winrate после первого enemy kill + 50% winrate после первой enemy death.
Источник — реальные opening kill и winner конкретного раунда; teamkills/suicides не используются.
Postplant = T wins / T planted rounds; retake = CT wins / CT rounds с planted bomb.
Plant opportunities/plants отдельно показываются в breakdown. Неполные bomb/combat данные не выдаются за подтверждённые события.

Side Performance = CT × 0.5 + T × 0.5 независимо от числа CT/T раундов.
Если сторона отсутствует, её score=null; используется доступная сторона, reliability общего компонента вдвое ниже её reliability.
CT/T не подменяются overall. Отсутствующие метрики исключаются из знаменателя весов и показываются unavailable.

### Economy

50% full-buy winrate + 15% force-buy winrate + 20% anti-eco + 15% pistol conversion.
Минимум применимых раундов: full-buy 1; остальные три компонента 5.
Редкие события до порога сохраняют raw_rate и sample, но не входят в score; затем доступные веса нормируются.
Это явное правило доступности, а не shrink-to-50 и не умножение score на reliability.
Pistol winrate, eco winrate и second-round recovery показываются диагностически.
Reset recovery недоступен: валидированных reset events в текущей структуре нет; значение не выдумывается.

### Map Execution

20% Trading + 20% Utility + 15% Opening + 10% Entrying + 15% Economy + 10% Postplant + 10% Retake.

Trading/Utility/Opening/Entrying строятся из взвешенных raw observations именно этой карты; Player Strength не является входом.
Нормализация — существующий empirical percentile V3 среди исторических команд именно на этой карте, с тем же cutoff/window/excluded series. При менее чем двух доступных peers normalized metric unavailable, а не искусственные 50.

- Trading: trade success rate 60%, death trade rate 40%.
- Utility: flash assists/round 30%, enemies flashed/flash 20%, enemy flash seconds/flash 15%, utility damage/round 30%, teammates flashed/flash 5% с обратным знаком percentile.
- Opening: opening success 70%, attempts/round 30%.
- Entrying: только реальные T opening contacts, T attempts/round 55%, T success 45%. Нулевой/отсутствующий opening sample не превращается в искусственный score.
- Economy — формула выше; Postplant/Retake — эффективность возможностей.

Firepower, Sniping, Clutching доступны в диагностическом Both/CT/T профиле при наличии соответствующих данных и не имеют дополнительного веса в Map Strength.
Количество использованных гранат, обычные kills и Player Strength не добавляются отдельными бонусами.

### Roster applicability

5/5 =1.0; 4/5 =0.8; 3/5 =0.6; 2/5 =0.2; 1/5 и 0/5 =0.
Unknown roster =0.1 с явным unknown sample и низкой reliability; он никогда не считается exact roster.
Используются фактические игроки demo либо подтверждённый demo roster. История не переписывается.

Дополнительное ограничение: если есть наблюдения 3+/5, общий вес 0–2/5 и Unknown не превышает 25% общего веса 3+/5. Например, 30 старых карт с 2/5 не перевешивают 3 exact карты. Исходный `roster_applicability` и итоговый `weight` возвращаются раздельно.
History window =730 дней, без freshness decay, last-5/10 и recent form компонентов.
Exact/4-of-5/3-of-5/older/unknown counts показываются раздельно.

EffectiveRosterService применяется в tournament/match context; для исторического запроса передаются выбранные исторические игроки и строгий knowledge cutoff временных overrides. Future и same-day published overrides исключаются. Permanent roster не меняется. Stand-in penalty не входит в Map Strength.

### Reliability

Обозначения (каждый фактор 0..1):

```
M = min(effective_maps / 12, 1)
R = min(effective_rounds / 300, 1)
C = exact_roster_maps / all_historical_maps
K = weighted ranking coverage
CT = min(weighted CT rounds / 150, 1)
T = min(weighted T rounds / 150, 1)
X = available Map Execution weight / configured weight
E = economy reliability / 100
P = postplant reliability / 100
Q = retake reliability / 100

Map reliability = 100 × sqrt(MR)
  × (0.25 + 0.75C)
  × (0.50 + 0.50K)
  × (0.50 + 0.25CT + 0.25T)
  × (0.40 + 0.60X)
  × (0.55 + 0.15E + 0.15P + 0.15Q)
```

Rate reliability = `100 × min(applicable opportunities / target, 1)`; target=40, для side round winrate=150; unavailable=0.
Profile reliability = `100 × sqrt(min(profile sample/target,1) × min(effective maps/20,1)) × available metric weight`.
Profile targets: Trading/Opening/Entrying/Clutching=40; Utility/Firepower/Sniping=400.
RQ reliability = `100 × min(effective maps/12,1) × (0.5+0.5K)`.
Составная reliability — сумма дочерних reliability по исходным весам, включая unavailable=0, без перенормировки отсутствующих весов.
**Ни одно из этих значений не умножается на score и не сдвигает его к 50.**

## API / temporal / зависимости

- GET `/api/v1/analysis/teams/{id}/maps-v3` — `maps: [{map, map_strength_v3: {...}}]`
- GET `/api/v1/analysis/teams/{id}/maps-v3/{map}` — `{map, map_strength_v3: {...}}`
- POST `/api/v1/analysis/teams/{id}/maps-v3/recalculate`

GET поддерживают `as_of`, `exclude_match_id`, `exclude_demo_id`, `tournament_id`, `match_id`.
При `match_id` используется дата матча и автоматически исключается серия. При `exclude_demo_id` исключается и вся известная связанная серия.
Все наблюдения удовлетворяют `event_date < as_of`; нет данных будущих игр, будущего ranking, будущей пятёрки или будущего override.
Пул берётся из MapPoolEntry и реально сыгранных исторических карт. Неигранные карты active pool возвращаются с null. Historical maps остаются доступны.

Нет входов Form V3, Veto, H2H, будущего opponent, odds, ML, LLM, Matchup или legacy score. Турнир выбирает effective roster, но не даёт score-бонус.
Существующие Team Strength/Form/Veto/H2H/Matchup формулы не менялись.
Runtime sanity проверяет диапазоны, NaN/Infinity, empty sample, side fallback, future observations/rankings, старую пятёрку с applicability=1 и dependency invariants.

## Проверки

- Backend полный suite: 878 passed, 2 skipped, 1 существующий StarletteDeprecationWarning.
- Maps V3: 50 passed (формулы, стороны, raw weighting, historical ranking, roster/override, future/self/series exclusion, пустая карта, API, snapshot, независимость от Team baseline и future opponent, отсутствие veto-влияния).
- Frontend: 31 passed в 9 test files; TypeScript + Vite production build успешен.
- `git diff --check`: без ошибок.
- Реальная PostgreSQL: 5 команд, все доступные карты, отдельный effective-roster context Vitality, API parity, совпадение baseline с живым Team V3 API для всех пяти команд и математическая проверка.
- Скрипт: `DEBUG=false .venv/bin/python scripts/check_map_strength_v35.py`.
- Полный машиночитаемый breakdown: [MAP_STRENGTH_V35_REAL_DATA.json](MAP_STRENGTH_V35_REAL_DATA.json).

## Реальные команды: все карты

Legacy ниже рассчитан существующим API для `current_roster`. Числа описывают локальную базу на момент проверки, не внешнюю оценку актуальной силы команд.

### Vitality

| Карта | V3 | Delta | CT | T | Reliability % | Maps / exact | Legacy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ancient | — | — | — | — | 0.00 | 0 / 0 | — |
| anubis | 41.52 | -15.30 | 39.98 | 54.81 | 26.53 | 9 / 7 | 23.78 |
| cache | 40.86 | -15.96 | 43.97 | 46.48 | 0.62 | 1 / 0 | — |
| dust2 | 57.94 | +1.12 | 55.95 | 59.54 | 43.88 | 13 / 10 | 46.67 |
| inferno | 60.33 | +3.51 | 61.93 | 52.58 | 17.86 | 6 / 6 | 61.81 |
| mirage | 59.52 | +2.70 | 54.80 | 52.34 | 21.58 | 7 / 6 | 56.03 |
| nuke | 61.97 | +5.15 | 61.00 | 48.72 | 34.76 | 10 / 8 | 62.25 |
| overpass | 74.31 | +17.49 | 62.13 | 72.99 | 4.71 | 3 / 3 | 74.69 |

### Spirit

| Карта | V3 | Delta | CT | T | Reliability % | Maps / exact | Legacy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ancient | 73.93 | +4.34 | 61.87 | 62.09 | 67.78 | 12 / 12 | 78.54 |
| anubis | 67.45 | -2.14 | 49.12 | 68.24 | 34.02 | 8 / 8 | 72.16 |
| cache | 63.38 | -6.21 | 51.74 | 62.63 | 33.70 | 7 / 7 | 54.95 |
| dust2 | 68.71 | -0.88 | 59.54 | 63.40 | 63.78 | 20 / 20 | 70.56 |
| inferno | — | — | — | — | 0.00 | 0 / 0 | — |
| mirage | 61.42 | -8.17 | 59.62 | 53.58 | 59.92 | 14 / 14 | 62.77 |
| nuke | 68.49 | -1.10 | 57.27 | 69.75 | 20.43 | 6 / 6 | 61.99 |
| overpass | 39.68 | -29.91 | 49.34 | 42.74 | 6.25 | 3 / 3 | 28.31 |

### MOUZ

| Карта | V3 | Delta | CT | T | Reliability % | Maps / exact | Legacy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ancient | 53.09 | -11.81 | 53.32 | 55.71 | 46.67 | 14 / 8 | 42.65 |
| anubis | — | — | — | — | 0.00 | 0 / 0 | — |
| cache | 80.94 | +16.04 | 84.17 | 45.50 | 2.15 | 1 / 1 | — |
| dust2 | 60.05 | -4.85 | 53.20 | 62.94 | 38.63 | 15 / 7 | 64.96 |
| inferno | 65.75 | +0.85 | 56.64 | 62.38 | 14.59 | 10 / 3 | 77.92 |
| mirage | 65.05 | +0.15 | 58.37 | 64.42 | 30.99 | 14 / 6 | 67.94 |
| nuke | 59.45 | -5.45 | 62.56 | 51.42 | 33.51 | 20 / 7 | 66.27 |
| overpass | 67.74 | +2.84 | 68.15 | 58.46 | 1.69 | 5 / 0 | — |

### G2

| Карта | V3 | Delta | CT | T | Reliability % | Maps / exact | Legacy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ancient | 50.60 | -8.91 | 53.85 | 47.59 | 26.09 | 13 / 5 | 42.57 |
| anubis | 51.88 | -7.63 | 52.25 | 53.50 | 18.65 | 7 / 5 | 46.55 |
| cache | 56.44 | -3.07 | 43.51 | 68.62 | 6.00 | 2 / 2 | — |
| dust2 | 48.08 | -11.43 | 42.31 | 54.84 | 18.16 | 12 / 3 | 38.80 |
| inferno | 68.46 | +8.95 | 59.56 | 59.21 | 28.57 | 11 / 5 | 78.18 |
| mirage | 59.97 | +0.46 | 54.61 | 62.48 | 23.63 | 15 / 4 | 62.48 |
| nuke | — | — | — | — | 0.00 | 0 / 0 | — |
| overpass | 65.71 | +6.20 | 66.08 | 59.85 | 1.77 | 5 / 0 | — |

### Falcons

| Карта | V3 | Delta | CT | T | Reliability % | Maps / exact | Legacy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ancient | 52.15 | -4.95 | 48.81 | 56.66 | 48.48 | 12 / 11 | 44.10 |
| anubis | 60.13 | +3.03 | 43.21 | 69.68 | 21.09 | 7 / 7 | 65.54 |
| cache | — | — | — | — | 0.00 | 0 / 0 | — |
| dust2 | 61.02 | +3.92 | 50.81 | 62.64 | 59.57 | 19 / 18 | 66.86 |
| inferno | 50.34 | -6.76 | 56.38 | 49.38 | 23.92 | 7 / 7 | 47.47 |
| mirage | 50.57 | -6.53 | 56.25 | 48.79 | 35.82 | 11 / 10 | 47.01 |
| nuke | 59.96 | +2.86 | 63.91 | 43.87 | 13.62 | 6 / 5 | 54.36 |

## Примеры для ручной проверки

- Сильная карта: Vitality Overpass, положительный delta, но малая выборка.
- Слабая: Spirit Overpass — большой отрицательный delta.
- CT-heavy: MOUZ Cache; у Falcons Nuke также заметно сильнее CT.
- T-heavy: Spirit Anubis и Falcons Anubis.
- Маленькая выборка: MOUZ Cache — одна exact карта, высокий score, низкая reliability.
- Нет карты: Vitality Ancient и Spirit Inferno — null, не 50.

## Vitality — временная замена jL вместо mezii

Контекст `tournament_id=7`. Permanent игроки: apEX / ZywOo / flameZ / ropz / mezii.
Effective: apEX / ZywOo / flameZ / ropz / jL. Исторические карты с mezii имеют 4/5, а не 5/5 применимость.

| Карта | V3 | Delta | CT | T | Reliability % | exact / 4-of-5 / 3-of-5 / older |
|---|---:|---:|---:|---:|---:|---|
| ancient | — | — | — | — | 0.00 | 0 / 0 / 0 / 0 |
| anubis | 43.48 | -13.34 | 40.76 | 53.72 | 11.74 | 2 / 7 / 0 / 0 |
| cache | 40.90 | -15.92 | 43.97 | 46.48 | 3.27 | 1 / 0 / 0 / 0 |
| dust2 | 60.43 | +3.61 | 56.60 | 60.38 | 19.97 | 3 / 10 / 0 / 0 |
| inferno | 61.07 | +4.25 | 61.93 | 52.58 | 3.17 | 0 / 6 / 0 / 0 |
| mirage | 58.64 | +1.82 | 54.93 | 51.19 | 6.87 | 1 / 6 / 0 / 0 |
| nuke | 62.58 | +5.76 | 62.02 | 48.62 | 13.89 | 2 / 8 / 0 / 0 |
| overpass | 73.47 | +16.65 | 62.13 | 72.99 | 0.87 | 0 / 3 / 0 / 0 |

## Ручной полный расчёт: Vitality Nuke

Results Quality = 67.90.
Side Performance = (61.00 + 48.72) / 2 = 54.86.
Map Execution = 59.00.

```
Map Strength = 67.90 × 0.45
             + 54.86 × 0.25
             + 59.00 × 0.30
             = 61.9700
             → round(..., 2) = 61.97

API score        = 61.97
Team Strength V3 = 56.82
Delta            = 61.97 − 56.82 = +5.15
```

Все три компонента доступны, effective weights равны 0.45/0.25/0.30. Скрипт проверяет равенство с живым HTTP API assert-ом.

Детализация Map Execution:

| Компонент | Score | Вес | Contribution |
|---|---:|---:|---:|
| trading | 49.41 | 0.2000 | 9.88 |
| utility | 47.79 | 0.2000 | 9.56 |
| opening | 77.65 | 0.1500 | 11.65 |
| entrying | 82.79 | 0.1000 | 8.28 |
| economy | 66.94 | 0.1500 | 10.04 |
| postplant | 69.71 | 0.1000 | 6.97 |
| retake | 26.21 | 0.1000 | 2.62 |

Детализация CT:

| Компонент | Score | Вес | Contribution |
|---|---:|---:|---:|
| round_winrate | 66.02 | 0.3500 | 23.11 |
| opening | 67.84 | 0.2000 | 13.57 |
| economy | 77.85 | 0.1500 | 11.68 |
| retake | 26.21 | 0.1500 | 3.93 |
| conversion_recovery | 58.14 | 0.1500 | 8.72 |

Детализация T:

| Компонент | Score | Вес | Contribution |
|---|---:|---:|---:|
| round_winrate | 43.11 | 0.3000 | 12.93 |
| opening | 38.58 | 0.2000 | 7.72 |
| economy | 45.45 | 0.1500 | 6.82 |
| postplant | 69.71 | 0.2000 | 13.94 |
| conversion_recovery | 48.75 | 0.1500 | 7.31 |

Наблюдения Results Quality (ranking на дату карты):

| Date | Rank | W/L | RD | Observation score | Applicability | Weight |
|---|---:|---|---:|---:|---:|---:|
| 2026-07-25 | None | L | -4 | 25.53 | 1.00 | 1.0000 |
| 2026-06-11 | None | W | 5 | 75.16 | 1.00 | 1.0000 |
| 2026-08-13 | 32 | W | 9 | 77.39 | 1.00 | 1.0000 |
| 2026-06-15 | None | W | 2 | 73.08 | 1.00 | 1.0000 |
| 2026-05-14 | None | W | 1 | 72.39 | 1.00 | 1.0000 |
| 2026-05-13 | None | L | -5 | 24.84 | 1.00 | 1.0000 |
| 2026-05-14 | None | W | 2 | 73.08 | 1.00 | 1.0000 |
| 2026-08-22 | 1 | W | 2 | 89.38 | 1.00 | 1.0000 |
| 2026-08-29 | 8 | W | 7 | 89.04 | 0.80 | 0.8000 |
| 2026-08-31 | 5 | W | 2 | 87.21 | 0.80 | 0.8000 |

RQ = 651.8500 / 9.6000 = 67.90.

Reliability factors: `{"maps": 0.7999999999999999, "rounds": 0.6839999999999999, "exact_roster_coverage": 0.8, "ranking_coverage": 0.375, "ct_sample": 0.6906666666666667, "t_sample": 0.6773333333333333, "execution_coverage": 1.0, "economy_sample": 0.6995, "postplant_sample": 1.0, "retake_sample": 1.0}`. Подстановка в формулу выше даёт 34.76%. Score остаётся 61.97.

Итерация V3.5 завершена. Следующая итерация не начата.
