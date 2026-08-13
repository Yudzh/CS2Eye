# Leadership Analytics: IGL Strength и Coach Impact

## Разделение оценок

Player Strength V2 описывает индивидуальную игровую силу. IGL Strength описывает
командные management-сигналы в контексте `player + team + current roster`.
Captain Strength — только presentation metric: `35% Player Strength + 65% IGL
Strength`. Coach Impact — отдельная корреляционная оценка периода тренера. Ни одна
из новых оценок не входит в Player, Team, Map Strength или Matchup Score.

## Management context и tenure

Текущий IGL определяется только активной `TeamParticipantMembership` основного
игрока с `role=igl`; coach — активной membership с `participant_type=coach`, отдельно
от пятёрки. Контекст связан с `teams.current_roster_id`. Начало — наиболее поздняя
достоверная дата из membership `joined_at` и `TeamRoster.active_from`; окончание
текущего периода отсутствует. Историческая смена роли внутри одной membership не
версионируется проектом, поэтому прошлые роли не угадываются и API сообщает
`role_history_status=current_only`. Смена team/IGL/coach создаёт другой membership
и тем самым другой management context; смешение между командами не допускается.

## Expected performance и residual

Baseline не использует IGL/Coach scores, поэтому circular dependency отсутствует:

```text
Expected Performance =
55% mean active-player Player Strength
+ 30% mean current-roster Map Strength
+ 15% opponent-rank baseline
```

Missing blocks перераспределяются. В текущем aggregate-level V1 opponent baseline
нейтрален (50); сильные соперники отдельно отражены существующими Top-15/Top 16–30
scopes. Actual — среднее существующего map performance (`60% map WR + 40% round
WR`) по current-roster maps. `management_residual = actual - expected`, а
normalized residual score — `clamp(50 + residual × 2)`.

## IGL Strength (`igl_v1`)

- 25% team overperformance vs expected;
- 20% T-side quality: T round WR, opening conversion/recovery, postplant, trades;
- 15% full-buy tactical: full-buy-vs-full-buy с force-vs-full и anti-eco;
- 15% opening management: conversion 5v4 и recovery 4v5;
- 10% postplant;
- 10% trading/teamplay;
- 5% Top-15/Top 16–30 performance.

Каждый блок возвращает raw/normalized score, configured/effective weight, impact,
sample, confidence и explanation через Scoring V2. Missing не равен нулю.

## Coach Impact (`coach_v1`)

- 30% team overperformance vs expected;
- 20% veto quality;
- 20% map-pool development;
- 15% strong-opponent preparation;
- 10% roster/player development;
- 5% residual consistency.

Veto quality доступен только при фактическом veto текущего roster: own picks,
opponent picks, deciders и selection/ban tendency рассматриваются вместе. Missing
veto исключается, а не штрафует coach. Map development сравнивает regressed recent
performance с current-roster baseline по нескольким картам. Opponent preparation
— residual Top-30 performance относительно expected. Consistency штрафует variance
map residuals, но имеет только 5%.

Player development остаётся unavailable: проект не хранит исторические snapshots
Player Strength, а приписывать текущую разницу тренеру нельзя. Reliability coach
понижается при неполном roster context и малой current-roster выборке. Это снижает
attribution при одновременной смене coach/IGL/players.

## Reliability и API

Base reliability использует `maps / (maps + 12)` для IGL и более консервативный
`maps / (maps + 15)` для coach, затем учитывает coverage факторов и roster
attribution. Score стягивается к 50.

- `GET /api/v1/analysis/teams/{id}/leadership`;
- Team detail получает `leadership`;
- Player detail получает `igl` и `captain_strength` только для активного IGL;
- Team Compare sides получают standalone leadership blocks.

## Attribution limitations

Фраза «команда overperformed baseline на +X в этот период» корректна; «coach/IGL
причинил +X» — нет. V1 допускает partial overlap team-overperformance между IGL и
coach: T-side/execution преимущественно относится к IGL, veto/map development — к
coach. Это attribution model, не causal proof.

Timeout effectiveness явно `not_available`: надёжных timeout events/ticks нет.
Также отложены role-history snapshots, полноценные pre/during/post tenure cohorts,
возрастная коррекция player development и causal controls для одновременных замен.
