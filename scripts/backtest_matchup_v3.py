"""Read-only real-data backtest comparing matchup_v1 vs matchup_v3 as pseudo-probabilities
of team_a series win, against the 50/50 baseline. Uses the same proper-scoring-rule metrics
(Brier, LogLoss, ROC-AUC, Accuracy) as the Win Probability V1 report in
docs/ITERATION_19_WIN_PROBABILITY.md, so the two tables are directly comparable.

Run with: DEBUG=false .venv/bin/python scripts/backtest_matchup_v3.py
"""
import asyncio
from math import log

from cs2eye.db.session import AsyncSessionLocal
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService


def clip(p: float, eps: float = 1e-6) -> float:
    return min(1 - eps, max(eps, p))


def metrics(pairs: list[tuple[float, int]]) -> dict:
    """pairs: (predicted_prob_team_a_wins, actual_team_a_won)."""
    n = len(pairs)
    if not n:
        return {"n": 0}
    brier = sum((p - y) ** 2 for p, y in pairs) / n
    logloss = -sum(y * log(clip(p)) + (1 - y) * log(1 - clip(p)) for p, y in pairs) / n
    accuracy = sum((p > .5) == bool(y) for p, y in pairs) / n
    positives = [p for p, y in pairs if y == 1]
    negatives = [p for p, y in pairs if y == 0]
    if positives and negatives:
        wins = sum((a > b) + .5 * (a == b) for a in positives for b in negatives)
        auc = wins / (len(positives) * len(negatives))
    else:
        auc = None
    return {"n": n, "brier": round(brier, 4), "log_loss": round(logloss, 4),
            "accuracy": round(accuracy, 4), "roc_auc": None if auc is None else round(auc, 4)}


async def main():
    async with AsyncSessionLocal() as session:
        v1_examples, v1_meta = await AnalyticsAsOfService(session).build_dataset("pre_veto")
    print(f"matchup_v1 dataset: {v1_meta['eligible']} eligible / {v1_meta['total_series']} total "
          f"(coverage {v1_meta['coverage']:.2%}); excluded={v1_meta['excluded_reasons']}")

    async with AsyncSessionLocal() as session:
        v3_examples, v3_meta = await AnalyticsAsOfService(session).build_dataset_v3("pre_veto")
    print(f"matchup_v3 dataset: {v3_meta['eligible']} eligible / {v3_meta['total_series']} total "
          f"(coverage {v3_meta['coverage']:.2%}); excluded={v3_meta['excluded_reasons']}")

    # Fair comparison: only series eligible under BOTH pipelines (v3's extra reliability
    # gates on Map/Team Strength V3 may exclude series v1 could still score, and vice versa).
    v1_by_id = {x.series_id: x for x in v1_examples}
    v3_by_id = {x.series_id: x for x in v3_examples}
    common = sorted(set(v1_by_id) & set(v3_by_id))
    print(f"common series scored by both: {len(common)}")

    baseline_pairs = [(.5, v1_by_id[sid].target) for sid in common]
    v1_pairs = [(v1_by_id[sid].matchup["team_a"]["score"] / 100, v1_by_id[sid].target) for sid in common]
    v3_pairs = [(v3_by_id[sid].matchup["team_a"]["score"] / 100, v3_by_id[sid].target) for sid in common]

    report = {"50/50 baseline": metrics(baseline_pairs),
              "matchup_v1 (raw score as p)": metrics(v1_pairs),
              "matchup_v3 (raw score as p)": metrics(v3_pairs)}
    print()
    header = f"{'model':<28}{'n':>5}{'brier':>9}{'log_loss':>11}{'roc_auc':>10}{'accuracy':>10}"
    print(header)
    for name, row in report.items():
        if row["n"] == 0:
            print(f"{name:<28} no data")
            continue
        print(f"{name:<28}{row['n']:>5}{row['brier']:>9}{row['log_loss']:>11}"
              f"{('-' if row['roc_auc'] is None else row['roc_auc']):>10}{row['accuracy']:>10}")


if __name__ == "__main__":
    asyncio.run(main())
