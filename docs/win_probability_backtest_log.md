# Win Probability Backtest Log

One entry per run of `scripts/backtest_win_probability_holdout.py`, newest first. This is the reference point for whether calibration is drifting over time -- compare a new entry's calibration table against the previous one for the same `mode`.

## 2026-09-18 -- model v12 (pre_veto)

- trained_at: 2026-09-16T08:01:10.999574+00:00
- quality_gate_passed: True
- holdout sample size: 30 matches (2026-08-23 .. 2026-09-06)
- accuracy: 0.8000
- brier_score: 0.1796 (coin flip: 0.25)
- log_loss: 0.5591

| bucket | count | avg predicted | actual win rate |
|---|---|---|---|
| 50-60% | 7 | 52.1% | 85.7% |
| 60-70% | 6 | 65.3% | 83.3% |
| 70-80% | 5 | 71.6% | 40.0% |
| 80-100% | 12 | 93.2% | 91.7% |

Note: sample size is small (30 matches, 5-12 per bucket) -- the 70-80% inversion is a signal to watch, not yet a confirmed miscalibration. Two of the six wrong picks involved Natus Vincere (excluded from betting decisions by the existing `navi_no_match_winner_bets` rule) and two involved Vitality playing with a confirmed stand-in (jL for mezii, per `tournament_roster_overrides`) -- excluding those four brings accuracy to ~92% (23/26).
