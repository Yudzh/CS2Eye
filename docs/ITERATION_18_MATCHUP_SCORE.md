# Iteration 18 — Matchup Score V1

## Meaning

Matchup Score answers how well Team A's current characteristics fit against Team B in a specified BO1/BO3/BO5. It is not Team Strength and not win probability. The scale is analytical: 0–100, 50 neutral; the returned Team A and Team B scores are exact complements.

Model version: `matchup_v1`.

## Formula

Configured upper weights are centralized in `analytics/matchup_config.py`:

| Factor | Weight |
|---|---:|
| Map Pool / Veto | 35% |
| Team Strength V2 | 25% |
| Current roster / form | 15% |
| Tactical matchup | 10% |
| H2H | 10% |
| Leadership / context | 5% |

Unavailable factors have zero effective weight; their configured weight is proportionally redistributed among available factors. For each available factor:

`impact = (factor_score - 50) × effective_weight`

`raw_score = clamp(50 + Σ impacts, 0, 100)`

`final_score = 50 + (raw_score - 50) × reliability`

Team B is `100 - Team A final_score`. Advantage is `score - 50`. Labels use distance from 50: below 3 neutral, 3–10 slight, 10–20 moderate and 20+ strong. They never describe probability.

Reliability is the configured-weighted mean of confidence for available factors. It combines Team Strength reliability, map/veto confidence, current roster map/freshness coverage, tactical coverage, H2H sample/freshness and Leadership availability. Levels are low below 0.45, medium below 0.75, otherwise high.

## Map/Veto factor

The existing Calculated Veto `v1.1` remains the only calculated veto engine. Each relevant map supplies a pairwise-symmetrized matchup score:

`map_score_A = (source_A + 100 - source_B) / 2`

`Map/Veto = 50 + Σ((map_score_A - 50) × playability_weight)`

`playability_weight` is analytical relevance, not probability.

- BO1 ranks maps by resistance to both teams' ban scores. The most playable remaining map dominates; other maps retain only a small uncertainty contribution.
- BO3 consumes the Calculated Veto scenarios. Team A pick and Team B pick each carry 40%, the decider 20%, and likely bans only trace weight. When first actor is unknown both scenarios are averaged.
- BO5 uses the five most playable active maps and leaves the remaining likely bans with minimal contribution. It does not reuse BO3 action assumptions.
- `pre_veto` always uses Calculated Veto.
- `post_veto` requires `series_id` and uses persisted `MatchVetoAction` picks/decider. Bans receive trace weight. The action must belong to the selected teams and be available by `as_of`.

## Team Strength and current roster

The service consumes existing Team Strength V2 outputs and reliability. It never recalculates or changes Player/Team/Map Strength.

Current roster/form comes from the existing Calculated Veto map signals. Current-roster scopes are smoothly blended with organization history by existing `sample_reliability`; recent 5/10/20 selection and freshness remain owned by the existing aggregate engine. There is no hard roster switch. Old roster rows do not enter the current-roster scope.

## Tactical matchup

Tactical weights are internal to the 10% upper factor:

| Component | Internal weight |
|---|---:|
| CT/T cross-matchup | 25% |
| Bomb/postplant/retake | 20% |
| Combat + contextual Round Swing | 20% |
| Economy | 15% |
| Utility | 10% |
| Trading/teamplay | 10% |

CT/T compares A T with B CT and A CT with B T. Bomb compares postplant against opposing retake in both directions. Economy includes full-buy as the central signal plus force, pistol/conversion and anti-eco. Utility uses existing damage, flash and assist aggregates without spatial inference. Trading stays a coordination signal.

Round Swing is read from current-roster, map-specific profiles inside the combat component. It is contextual and pairwise: it is not added as another upper factor. Raw opening and clutch evidence remain small supporting combat context. There are no independent large Opening Swing, Clutch Swing or Trade Swing factors, preventing repeated event credit. General Swing already present through Player Strength → Team Strength is therefore not given another large standalone weight.

Every tactical component is symmetrized from both sides before aggregation. Missing components are reweighted, never treated as zero.

## H2H and Leadership

H2H priority is current-roster H2H when maps exist, otherwise organization H2H. Existing recency weighting, sample shrinkage and confidence are preserved. No meetings means unavailable, not negative. Map relevance is exposed for future map-H2H refinement; V1 uses the selected H2H slice score.

Leadership is optional and has only 5% configured upper weight. Within each team it is 60% IGL and 40% Coach, reweighted if one is missing. Missing Leadership does not penalize. LAN/stage/elimination context is not invented where no reliable series metadata is supplied.

## API and UI

`GET /api/v1/analysis/matchup`

Parameters: `team_a_id`, `team_b_id`, `format=bo1|bo3|bo5`, `analysis_mode=pre_veto|post_veto`, optional `as_of`, and `series_id` for post-veto.

The response contains version and non-probability semantics, symmetric teams, raw/final scores, reliability/confidence, advantage, mathematical factor breakdown, relevant map contributions, tactical components, veto basis and limitations.

Team Compare loads one Matchup response for its top Matchup block. The UI supports format and pre/post-veto controls, loading/errors, factor impacts, relevant maps and explicit explanations that the score is not probability.

## Historical safety and leakage

`calculate(team_a, team_b, as_of, format, analysis_mode)` is the service boundary intended for Iteration 19 backtesting. `pre_veto` never reads actual veto.

Current Team Strength, current roster, active Leadership, current normalized Swing artifact and precomputed TeamMapAggregate rows are not temporal snapshots. For `as_of` earlier than today V1 follows a strict safe fallback: these unsafe factors are marked unavailable and the result remains neutral with zero reliability rather than leaking future state. Post-veto actions are accepted only for the selected series and only when the match date is not after `as_of`.

This makes historical calls safe but intentionally uninformative until temporal Strength/map/Swing snapshots exist. Full temporal reconstruction and versioned Swing-model backtesting remain Iteration 19 work. The analyzed match is not read through current aggregates in this strict mode.

## Known limitations

- Historical `as_of` returns a safe neutral result until temporal aggregate snapshots are implemented.
- Map-specific H2H is exposed by the H2H framework but not yet separately blended inside each selected map contribution.
- BO1/BO5 use analytical relevance derived from existing ban scores; they do not claim to simulate official veto probability.
- Model activation/version policy for Round Swing remains the Round Swing V1 policy.
