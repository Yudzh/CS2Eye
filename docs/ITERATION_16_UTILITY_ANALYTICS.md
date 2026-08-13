# Итерация 16 — Utility Analytics

## Источник demoparser2 0.41.4

Контракт проверен на реальной CS2 demo. `grenade_thrown` предоставляет `tick`, `user_name`, `user_steamid`, запрошенные player properties `user_team_num`/`user_team_clan_name` и `weapon`. Поддерживаются `hegrenade`, `flashbang`, `smokegrenade`, `molotov`, `incgrenade`/`incendiary`; fire-типы сохраняют raw type, но агрегируются вместе. `decoy` сохраняется отдельно и не входит в total utility.

`player_hurt` предоставляет `tick`, attacker/user identity и team properties, `weapon`, `dmg_health`, warmup/technical/restart properties. HE — `weapon=hegrenade`; fire — `inferno`, `molotov`, `incgrenade` или `incendiary`. В основной damage входит только enemy health damage. Teammate и self health damage сохраняются отдельными counters. Все fire damage ticks суммируются.

В game-event list этой версии нет `player_blind`. Поэтому flash targets точно читаются из `flashbang_detonate` (`tick`, owner identity) и player properties `flash_duration`, `flash_max_alpha`, `team_num`, `team_clan_name` на tick детонации. Это даёт enemies/teammates flashed и duration. `player_death.assistedflash=true` с `assister_*` является источником flash assists; собственная эвристика не используется.

## Нормализация и формулы

`DemoUtilityEvent` хранит только normalized event kind, tick, gameplay round, owner/team/side, normalized и raw grenade type, optional target/relation, damage и flash duration. Throws, damage ticks, flash targets и flash assists целиком заменяются при reparse. Warmup, technical, restart, freeze/post-round gaps, post-match cleanup и любые события вне accepted normalized gameplay-round intervals исключаются без ложного `needs_review`.

`DemoPlayerStat.utility_data` и `DemoTeamUtilityStat.utility_data` содержат raw counters и CT/T split. `TeamMapAggregate.utility_data` использует существующие organization/current-roster, all, recent:5/10/20 и opponent rank scopes. Rates делятся на valid gameplay rounds; per-grenade rates при нулевом denominator равны `null`, а не нулю. `utility_damage = enemy HE damage + enemy fire damage`. Decoy не входит в `total_utility_thrown`.

Статус `utility_data_status`: старые demo — `not_parsed`; только `complete` участвует в aggregates. Неполные rounds дают `partial/needs_review`. Damage без соответствующего throw или flash effect без flash throw даёт `needs_review`. Отсутствие rows не интерпретируется как performance=0.

## API и UI

`GET /api/v1/demos/{demo_file_id}/utility-stats` возвращает status, team/player stats и CT/T. Player detail возвращает overall, recent 5/10/20, Top-15, Top 16–30 и map scopes. Team Maps и Team Compare получают utility через существующий aggregate/API contract. Demo, Player и Team Maps UI показывают objective utility components без Utility Score. Scoring Model V2 и его weights не изменены.

## Ограничения

Inventory state на death не извлекается достаточно надёжно: utility-left-on-death отсутствует (`null`). В normalized bomb lifecycle сохраняется факт plant, но не точный plant tick, поэтому retake utility не классифицируется. Execute/defensive utility отложена: без bombsite, positions, timing/site-entry context такая классификация была бы эвристикой. Spatial smoke quality также не оценивается. Tick-rate conversion для реализованных метрик не нужен.

Migration `0020_utility_analytics` сохраняет старые demo и выставляет `not_parsed`. Для данных требуется штатный reparse с `replace_existing=true`; delete-and-replace делает events/team/player stats идемпотентными, после чего пересчитываются organization и roster aggregates.
