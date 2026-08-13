# Iteration 19 — Win Probability V1

## Semantics

`Matchup Score` is an analytical 0–100 matchup score. `Win Probability` is a
calibrated estimate of series victory learned from historical pre-match rows.
They are deliberately shown as separate values.

## Temporal reconstruction

`AnalyticsAsOfService` bulk-loads matches, normalized demo/map/player/team
analytics, historical rankings, rosters and veto actions in 13 bounded SQL
queries. It then iterates series chronologically. Features are calculated from
the rolling state before the series and the completed series is added only
after prediction. Because `Match` currently has `match_date` rather than an
exact start time, every series on the same date sees state from before that
date. This conservative rule prevents same-day leakage.

Historical roster is the last complete `DemoTeamRoster` before the cutoff.
Historical ranking is the latest `TeamRankingSnapshot.ranking_date <= as_of`.
Player, Team and Map inputs use only normalized demos already present in the
rolling state. Recent 5/10 uses the last maps before `as_of`; H2H and veto
profiles likewise contain only prior series. The predicted series cannot enter
its own features.

Strict historical mode excludes two unsafe signals:

- Round Swing, because the active Round Swing V1 artifact was trained using
  matches that are in the future relative to early backtest rows;
- IGL/Coach impact where a reliable historical role-tenure snapshot cannot be
  reconstructed.

Missing unsafe signals are unavailable/neutral rather than zero-valued
penalties.

## Dataset and split (2026-08-13)

- completed historical series: 106;
- eligible strict pre-veto rows: 47;
- coverage: 44.34%;
- excluded: 59 (`insufficient_history`: 57,
  `missing_historical_roster`: 2);
- Team A wins: 25; Team B wins: 22;
- available range: 2026-06-05 through 2026-08-02;
- train: 32 series (2026-06-05 through 2026-06-20);
- validation: 7 series (2026-06-21 through 2026-07-26);
- test: 8 series (2026-07-27 through 2026-08-02).

The split is chronological 70/15/15 and never divides one series across sets.

## Features

Feature schema: `matchup_features_v1`.

- centered Matchup Score and raw Matchup Score;
- reliability-weighted matchup advantage;
- historical Team Strength difference;
- Map/Veto, roster form, tactical, H2H and Leadership advantages;
- historical ranking advantage;
- BO1/BO3/BO5 interactions with Team Strength.

All directional features are oriented to Team A. Inference averages both team
orientations, enforcing `P(A,B) = 1 - P(B,A)` and an exactly neutral prediction
for neutral features.

## Model and real backtest

Model version: `v1`. Model type: standardized L2 logistic regression. Raw
logistic calibration is retained; the validation/test sample is too small to
fit a defensible Platt or isotonic calibration layer.

| Model | Brier | Log Loss | ECE | ROC-AUC | Accuracy |
|---|---:|---:|---:|---:|---:|
| 50/50 baseline | 0.2500 | 0.6931 | 0.1250 | 0.5000 | 0.6250 |
| Team Strength baseline | 0.3100 | 0.8237 | 0.2648 | 0.4000 | 0.5000 |
| Matchup baseline | 0.3047 | 0.8181 | 0.5347 | 0.4000 | 0.6250 |
| Win Probability V1 candidate | 0.2652 | 0.7242 | 0.2043 | 0.5333 | 0.5000 |

Candidate calibration bins on the eight-series test set:

| Predicted range | Average prediction | Actual win rate | Samples |
|---|---:|---:|---:|
| 30–40% | 36.08% | 66.67% | 3 |
| 45–50% | 47.75% | 50.00% | 2 |
| 55–60% | 56.05% | 100.00% | 1 |
| 60–70% | 61.62% | 50.00% | 2 |

Prediction distribution: min 0.3396, p10 0.3478, p25 0.3815, median 0.4775,
p75 0.5706, p90 0.6102, max 0.6313. There were no predictions below 20% or
above 80%.

The candidate does **not** outperform the 50/50 baseline on Brier or Log Loss.
It is stored for audit but intentionally not activated. The activation service
rejects a candidate that fails both proper-scoring-rule comparisons unless an
administrator explicitly uses `force=true`.

## Pre-veto and post-veto

Pre-veto historical features use only prior veto tendencies and historical map
performance. Actual veto of the predicted series is unavailable. Post-veto
mode may use that series' stored actual veto because it represents the moment
after map announcement but before play. Both modes remain separate in API and
prediction snapshots. UI can display their difference in percentage points.

Offline candidate sanity example (not a production prediction): for historical
BO3 series 102, FaZe vs The MongolZ on 2026-07-31, the candidate changed from
82.61% pre-veto to 68.10% post-veto for FaZe, an impact of -14.51 percentage
points. The unusually large move is another reason the candidate remains
inactive until the historical sample grows and calibration improves.

## Storage and operations

Migration `0023_win_probability_v1` creates JSON model artifacts and immutable
prediction snapshots. Training and activation are separate:

1. `POST /api/v1/analysis/win-probability/train`;
2. inspect metrics through `GET /api/v1/analysis/win-probability/status`;
3. `POST /api/v1/analysis/win-probability/activate/{artifact_id}`;
4. optional `POST /api/v1/analysis/win-probability/backtest`;
5. save a live prediction with `POST /api/v1/analysis/predictions`.

Training is manual. New demos refresh existing analytics but do not retrain the
probability model.

## Limitations

- Only 47 eligible series and 8 test rows are currently available. Calibration
  conclusions are unstable and production activation is not justified.
- Match start time is not stored; the safe cutoff has day granularity.
- Strict backtests exclude Round Swing and historical Leadership until temporal
  model/role versions exist.
- Historical calculated veto is a rolling V1 approximation rather than a
  persisted snapshot of the full current Calculated Veto engine.
- Per-map probability is not exposed: current data cannot validate a separate
  calibrated map model.
