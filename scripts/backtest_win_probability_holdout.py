"""Out-of-sample backtest of the ACTIVE Win Probability model on matches it never trained on.

Reuses the exact production pipeline (AnalyticsAsOfService.build_dataset_v3 +
temporal_split, the same 70/15/15 chronological split win_probability_service.
train_win_probability and backtest_win_probability use), so "test" here is precisely
the last 15% of eligible historical series by match_date -- the same slice the active
model was itself evaluated against at training time. Each row's features are computed
as-of that match's own date (strictly before it; matchup_v3's own cutoff policy), i.e.
exactly what the ML pick would have looked like the day before the match was played.

Read-only: no session.commit(), nothing written to the database. Only reads.

Output:
  - a per-match table (date, team_a, team_b, P(team_a), predicted pick, actual winner,
    correct) written as CSV to --out (default: a temp file, path printed at the end)
  - accuracy, Brier score
  - calibration by pick-confidence bucket (50-60/60-70/70-80/80+): for each bucket,
    predicted average confidence vs. actual win rate of the pick. A gap here (e.g. the
    model says 70-80% but the pick only wins ~55% of the time) means probabilities are
    overconfident and should not be surfaced to a client as-is.
  - a dated entry (model version, sample size, accuracy, Brier, calibration table)
    prepended to docs/win_probability_backtest_log.md, so a run a month from now has
    something to diff against instead of relying on memory or chat history.

Cost: build_dataset_v3 walks every eligible historical series chronologically and calls
MapStrengthV3Service/TeamStrengthV3Service per match -- this is the same expensive full
rebuild scripts/train_v3_candidate_model.py pays for; expect it to take a while on the
full history.

Run with: DEBUG=false .venv/bin/python scripts/backtest_win_probability_holdout.py [--mode pre_veto|post_veto] [--out PATH]
"""
import argparse
import asyncio
import csv
import os
from datetime import date

from sqlalchemy import select

from cs2eye.analytics.win_probability import WinProbabilityModel, probability_metrics, temporal_split
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.team import Team
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.win_probability_service import active_model

CONFIDENCE_BUCKETS = ((.5, .6), (.6, .7), (.7, .8), (.8, 1.000001))
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "win_probability_backtest_log.md")
LOG_HEADER = ("# Win Probability Backtest Log\n\n"
              "One entry per run of `scripts/backtest_win_probability_holdout.py`, newest first. "
              "This is the reference point for whether calibration is drifting over time -- compare "
              "a new entry's calibration table against the previous one for the same `mode`.\n\n")


def build_pick_calibration(rows: list[dict]) -> list[dict]:
    buckets = []
    for low, high in CONFIDENCE_BUCKETS:
        items = [row for row in rows if low <= row["confidence"] < high]
        if not items:
            buckets.append({"bucket": f"{int(low * 100)}-{int(min(high, 1) * 100)}%", "count": 0,
                             "avg_predicted_confidence": None, "actual_pick_win_rate": None})
            continue
        avg_conf = sum(row["confidence"] for row in items) / len(items)
        win_rate = sum(1 for row in items if row["correct"]) / len(items)
        buckets.append({"bucket": f"{int(low * 100)}-{int(min(high, 1) * 100)}%", "count": len(items),
                         "avg_predicted_confidence": avg_conf, "actual_pick_win_rate": win_rate})
    return buckets


def build_log_entry(*, measured_at: str, mode: str, artifact, sample_size: int,
                     holdout_range: tuple[str, str], metrics: dict, calibration: list[dict]) -> str:
    lines = [
        f"## {measured_at} -- model {artifact.model_version} ({mode})", "",
        f"- trained_at: {artifact.trained_at.isoformat()}",
        f"- quality_gate_passed: {artifact.quality_gate_passed}"
        f"{' (forced_active)' if artifact.forced_active else ''}",
        f"- holdout sample size: {sample_size} matches ({holdout_range[0]} .. {holdout_range[1]})",
        f"- accuracy: {metrics['accuracy']:.4f}",
        f"- brier_score: {metrics['brier_score']:.4f} (coin flip: 0.25)",
        f"- log_loss: {metrics['log_loss']:.4f}",
        "", "| bucket | count | avg predicted | actual win rate |", "|---|---|---|---|",
    ]
    for bucket in calibration:
        if bucket["count"] == 0:
            lines.append(f"| {bucket['bucket']} | 0 | - | - |")
        else:
            lines.append(f"| {bucket['bucket']} | {bucket['count']} | "
                          f"{bucket['avg_predicted_confidence']:.1%} | {bucket['actual_pick_win_rate']:.1%} |")
    lines.append("")
    return "\n".join(lines)


def prepend_log_entry(entry: str, path: str = LOG_PATH) -> None:
    body = ""
    if os.path.exists(path):
        with open(path) as file:
            existing = file.read()
        body = existing[len(LOG_HEADER):] if existing.startswith(LOG_HEADER) else existing
    with open(path, "w") as file:
        file.write(LOG_HEADER + entry + "\n" + body)


async def main(mode: str, out_path: str) -> None:
    async with AsyncSessionLocal() as session:
        artifact = await active_model(session)
        if artifact is None:
            print("No active Win Probability model artifact found.")
            return
        print(f"active model: {artifact.model_version} (trained_at={artifact.trained_at.isoformat()}, "
              f"quality_gate_passed={artifact.quality_gate_passed}, forced_active={artifact.forced_active})")

        print(f"\nbuilding dataset via build_dataset_v3(mode={mode!r}) -- this walks the full "
              f"eligible history chronologically, can take a while...")
        rows, coverage = await AnalyticsAsOfService(session).build_dataset_v3(mode)
        print(f"dataset: {coverage['eligible']} eligible / {coverage['total_series']} total series "
              f"(coverage {coverage['coverage']:.2%}), date range "
              f"{coverage['date_range']['first']} .. {coverage['date_range']['last']}")

        train, validation, test = temporal_split(rows)
        print(f"split 70/15/15 chronological: train={len(train)} validation={len(validation)} "
              f"test(holdout)={len(test)}")
        print(f"holdout date range: {test[0].match_date.isoformat()} .. {test[-1].match_date.isoformat()}")

        team_ids = {item.team_a_id for item in test} | {item.team_b_id for item in test}
        teams = (await session.execute(select(Team).where(Team.id.in_(team_ids)))).scalars()
        names = {team.id: team.name for team in teams}

    model = WinProbabilityModel(artifact.artifact)
    probabilities = model.predict_symmetric([item.features for item in test])

    match_rows = []
    for item, p in zip(test, probabilities, strict=True):
        name_a, name_b = names.get(item.team_a_id, str(item.team_a_id)), names.get(item.team_b_id, str(item.team_b_id))
        predicted_winner = name_a if p >= .5 else name_b
        actual_winner = name_a if item.target == 1 else name_b
        match_rows.append({
            "date": item.match_date.isoformat(), "team_a": name_a, "team_b": name_b,
            "team_a_probability": round(p, 4), "predicted_winner": predicted_winner,
            "actual_winner": actual_winner, "correct": predicted_winner == actual_winner,
            "confidence": p if p >= .5 else 1 - p,
        })

    metrics = probability_metrics(probabilities, [item.target for item in test])
    print(f"\naccuracy: {metrics['accuracy']:.4f}   brier_score: {metrics['brier_score']:.4f} "
          f"(coin-flip baseline: 0.25)   log_loss: {metrics['log_loss']:.4f}")

    print(f"\n{'bucket':<10}{'count':>7}{'avg predicted':>16}{'actual win rate':>18}")
    for bucket in build_pick_calibration(match_rows):
        if bucket["count"] == 0:
            print(f"{bucket['bucket']:<10}{0:>7}{'-':>16}{'-':>18}")
            continue
        print(f"{bucket['bucket']:<10}{bucket['count']:>7}{bucket['avg_predicted_confidence']:>16.2%}"
              f"{bucket['actual_pick_win_rate']:>18.2%}")

    with open(out_path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["date", "team_a", "team_b", "team_a_probability",
                                                    "predicted_winner", "actual_winner", "correct"])
        writer.writeheader()
        for row in match_rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})
    print(f"\nper-match table written to: {out_path} ({len(match_rows)} rows)")

    entry = build_log_entry(
        measured_at=date.today().isoformat(), mode=mode, artifact=artifact, sample_size=len(test),
        holdout_range=(test[0].match_date.isoformat(), test[-1].match_date.isoformat()),
        metrics=metrics, calibration=build_pick_calibration(match_rows),
    )
    prepend_log_entry(entry)
    print(f"log entry prepended to: {os.path.abspath(LOG_PATH)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pre_veto", "post_veto"], default="pre_veto")
    parser.add_argument("--out", default="/tmp/win_probability_backtest_holdout.csv")
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.out))
