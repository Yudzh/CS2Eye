# CS2Eye Round Swing V1

Round Swing is the change in the modeled probability that the event player's team wins the current round. The single model predicts `P(T wins)`; CT values are inverted. Opening, trade, clutch, postplant and retake values are overlapping subsets of total Swing, never bonuses.

## State and model

V1 uses map, T/CT alive counts and their delta, planted/not-planted state, real freeze-end T/CT equipment values and their delta, and round time remaining when physical tick duration can be inferred from normalized round start/end/duration. Exact normalized plant ticks determine postplant state. Missing time/bomb-time values have explicit missing indicators; no 64-tick constant is embedded. HP, armor, kits, bombsite and bomb timer are excluded until they are reliably normalized.

The artifact is standardized L2 logistic regression implemented deterministically and stored as JSON coefficients/schema/metadata, not pickle. It returns `P(T wins)` in batch. Training samples are the before and after states of valid enemy kills in complete gameplay rounds. Winner is only the target. Temporal group split uses match-series ID (demo ID fallback), so states from one series cannot cross train/validation. Reported metrics are Brier score, log loss and 10-bin expected calibration error with reliability bins.

If no active `v1` artifact exists, inference returns `model_not_trained`; it never manufactures Swing. Manual endpoints are `POST /api/v1/admin/round-swing/train` and `POST /api/v1/admin/round-swing/recalculate/{demo_file_id}`.

## Attribution V1

One kill creates one probability transition. Its team-oriented Swing is split among enemy damage contributors to that victim earlier in the same round. The finisher has a minimum 20 damage-equivalent. A normalized `flash_assist` receives 10%, with 90% left for the damage split. The victim receives the opposite signed value for the player view, tagged `victim_non_additive`; team sums include only killer/damage-assist/flash-assist roles. Thus credited positive shares sum to exactly one event Swing, while the death is available without doubling a team metric.

Damage from an older encounter in the same round can currently remain in the allocation; this is the documented V1 limitation. Opening/trade/clutch flags only label the same transition. No hardcoded bonus exists.

## Aggregation and scoring

Raw player Swing/round is `100 * sum(credited probability deltas) / rounds`. Reliability is `rounds/(rounds+100)` and adjusted Swing regresses raw Swing toward the reference mean. Score 0–100 uses a historical median/MAD clipped z-score, with 50 as the reference median. Missing Swing is unavailable and reweights existing Player Strength inputs; it is not zero and does not penalize old data.

Player Strength model `v2.1` allocates 25% Internal Rating, 20% BO3, 15% Round Swing, 15% Top 1–15, 10% Top 16–30, 10% Recent Form and 5% Role Performance. Contextual Swing subsets are not separate factors. Team Strength receives Swing only through roster/player strength, never as a second direct factor.

## Storage, recalculation, limitations

Normalized damage and exact bomb lifecycle events are stored independently from parsing output. Before/after state, probabilities, attribution, contexts, confidence and model version are persisted per kill. A new model can therefore recalculate parsed demos without rerunning demoparser. Demos parsed before migration need one reparse to populate exact damage/bomb source events; afterward only Swing recalculation is required.

V1 equipment is the real freeze-end snapshot and is not updated after dropped/picked weapons. Exact bomb timer, HP, armor, kits and bombsite are not yet features. Historical normalization must be frozen per trained artifact before historical/as-of production predictions. Matchup integration must remain inside the existing tactical factor and awaits sufficient trained coverage; it must not increase the total tactical weight.
