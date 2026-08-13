# CS2Eye Round Swing V1

Round Swing is the change in the modeled probability that the event player's team wins the current round. The single model predicts `P(T wins)`; CT values are inverted. Opening, trade, clutch, postplant and retake are overlapping explanations of total Swing, never additive bonuses.

## State, model and data loading

V1 uses map, T/CT alive counts and their delta, planted/not-planted state, real freeze-end T/CT equipment values and their delta, and inferred round time remaining. Time uses normalized start/end ticks and physical round duration; no 64-tick constant is embedded. Exact normalized plant ticks determine postplant state. Missing time values have explicit indicators. HP, armor, kits, bombsite and bomb timer remain excluded because they are not yet reliably normalized.

The model is deterministic standardized L2 logistic regression stored as a JSON coefficient/schema/metadata artifact, not pickle. It performs batch inference. Training records are before and after states of valid enemy kills in complete gameplay rounds; winner is target-only and no future state is a feature.

The training builder performs exactly three bounded SQL queries regardless of match/round count: one bulk query for rounds/map/demo context, one for all relevant kills, and one for all relevant bomb events. Grouping and state assembly then happen in memory. A semantic fixture compares bulk assembly with the former per-round construction.

## Production training baseline (2026-08-13)

Temporal group split uses namespaced `match:{id}` groups with `demo:{id}` fallback. A group never crosses the split. Older groups train and newer groups validate.

| Measure | Train | Validation |
|---|---:|---:|
| Match/demo groups | 119 | 30 |
| States | 57,688 | 18,732 |
| T-win targets | 25,206 | 8,582 |
| CT-win targets | 32,482 | 10,150 |
| Brier score | 0.142476 | 0.140394 |
| Log loss | 0.439684 | 0.435865 |
| ECE (10 bins) | 0.054426 | 0.060856 |

Validation calibration:

| Predicted range | Avg prediction | Actual T WR | Samples |
|---|---:|---:|---:|
| 0–10% | 5.70% | 1.07% | 2,055 |
| 10–20% | 15.11% | 4.83% | 2,215 |
| 20–30% | 25.37% | 15.84% | 1,970 |
| 30–40% | 34.60% | 30.39% | 1,905 |
| 40–50% | 45.12% | 43.17% | 2,152 |
| 50–60% | 55.06% | 58.28% | 1,896 |
| 60–70% | 64.83% | 70.13% | 1,898 |
| 70–80% | 74.86% | 83.33% | 1,890 |
| 80–90% | 84.97% | 92.86% | 1,666 |
| 90–100% | 94.11% | 99.08% | 1,085 |

There were 76,420 audited predictions: none at pathological near-0/near-1 thresholds, no negative Swing for a valid enemy kill, and no ordinary transition above 30 percentage points.

Real sanity cases include: 5v5 opening `45.46% → 63.92%` (`+18.46 pp`); 5v1 cleanup `93.73% → 96.95%` (`+3.22 pp`); planted CT 1v2→1v1 clutch transition `11.83% → 21.58%` (`+9.74 pp`); postplant retake kill `22.89% → 37.84%` (`+14.94 pp`). These values emerge from state probability, not event tables.

## Attribution V1

One kill creates one probability transition. The team-oriented Swing is split among enemy damage contributors to that victim earlier in the same round. The finisher has a minimum 20 damage-equivalent. A normalized `flash_assist` receives 10%, leaving 90% for the damage split. Positive credited shares sum to exactly one event Swing. The victim receives the opposite value tagged `victim_non_additive`, so player death impact is visible but team totals include only killer/damage-assist/flash-assist roles.

Damage from an older encounter in the same round can remain in allocation; this is a V1 limitation. Opening/trade/clutch flags only select the same transition. There is no opening, trade or clutch bonus.

## Distribution, normalization and reliability

After recalculation, 38,210 event transitions have event-Swing pp distribution: min `0.525`, p5 `3.040`, p25 `9.181`, median `14.362`, p75 `17.216`, p95 `18.441`, max `18.625`, mean `12.825`, std `5.013`.

Across 195 players, adjusted Swing/round is: min `-2.809`, p5 `-1.288`, p25 `-0.574`, median `-0.091`, p75 `0.493`, p95 `1.368`, max `2.589`, mean `-0.045`, std `0.864`.

Raw player Swing/round is `100 × sum(credited probability deltas) / rounds`. Reliability is `rounds/(rounds+100)` and adjusted Swing regresses raw Swing to the reference. The empirical score is:

`50 + clip((adjusted - median) / (1.4826 × MAD), -3, 3) × 50/3`

with median `-0.090867`, MAD `0.540066`, robust scale `0.800703`. Thus 50 is reference-median performance, not raw zero. Each overall/map/rank/recent scope calculates its own rounds and confidence. Missing data is unavailable (`null`), never a fake zero.

Supported player scopes are overall, per-map, historical opponent rank (`Top 1–15`, `Top 16–30` using the snapshot attached to that demo), and recent 5/10/20 demos.

## Double-counting audit and scoring

On 195 players, correlations of adjusted Swing/round were:

| Metric | Pearson | Spearman |
|---|---:|---:|
| Kills/round | 0.790 | 0.773 |
| ADR | 0.814 | 0.798 |
| Internal Rating | 0.851 | 0.863 |
| Opening success | 0.618 | 0.622 |
| Clutch rate | 0.186 | 0.196 |
| Trade rate | 0.193 | 0.182 |

Because Internal Rating overlap is high, final Player Strength `v2.1` uses 25% Internal Rating, 20% BO3, **10% Round Swing**, 15% Top 1–15, 10% Top 16–30, 15% Recent Form and 5% Role Performance. Missing Swing reweights available factors. Contextual Swing subsets are explanations, not extra Player Strength factors. Team Strength receives Swing only through roster quality.

Calculated Veto / Tactical Matchup is version `v1.1`. Swing is inside the existing economy/combat factor; it is not a new top-level weight. Overall roster Swing carries most combat-impact evidence, raw opening and clutch contributions are reduced, and trade rate remains as coordination evidence. Missing Swing renormalizes the available combat inputs. The breakdown reason explicitly reports Swing use or fallback.

Team Compare supplies current-roster overall and real per-map profiles: average, top two, bottom two, CT, T, opening, clutch, sample, confidence, source and model metadata. Map selection uses that map's player scope. Old roster members are excluded by the current roster fingerprint; small samples are labeled low-confidence rather than displayed as exact zero.

## Storage, retraining and runtime

Normalized damage and exact bomb lifecycle events are independent of model inference. Before/after state, probabilities, attribution, contexts, confidence and model version are persisted per kill. All 270 eligible historical demos were recalculated with model `v1`; repeating recalculation deletes/replaces a demo's events and does not duplicate them. Since normalized source data is now present, **no further reparse is required**—only Swing recalculation after a new model.

Training updates the active artifact only after training and metrics complete, in the surrounding DB transaction. A failed training computation therefore leaves the old active artifact intact. V1 has one active version slot and no separate approval/staging registry; operators should inspect metrics before committing an operational replacement.

### Normal usage

`Upload demo → parsing → persist normalized events → automatic Swing calculation → aggregates`

If no active model exists, parsing still succeeds and records `model_not_trained`. After a model is trained, the demo can be recalculated without parsing again.

### Periodic retraining

`POST /api/v1/admin/round-swing/train → inspect metrics → POST /api/v1/admin/round-swing/recalculate-all`

Training is manual. New demos use the active model; do not retrain after every upload. Normalization can be refreshed through the internal normalization endpoint after historical recalculation.

## Remaining V1 limitations

Equipment is the real freeze-end snapshot and is not updated after weapon drops/pickups. Exact bomb timer, HP, armor, kits and bombsite are not features. Same-round damage attribution has no shorter encounter window. Calibration is usable but visibly conservative at the extreme bins. The active artifact has transactional replacement but no candidate/approve lifecycle.
