"""Train a real matchup_features_v3 candidate through the actual production service
(win_probability_service.train_win_probability), not a hand-rolled copy of its logic --
this is the exact same code path POST /api/v1/analysis/win-probability/train?
feature_schema_version=matchup_features_v3 or the MLModelsPage "Train" button would run.

Schema: WIN_PROBABILITY_FEATURES_V3 -- a forward-selection starting set that grows over
time (see the comment in cs2eye/analytics/win_probability_config.py for the full history:
6 v1 features cut for matchup_v3 outright, then a further round of near-duplicates found
by diagnostics on the resulting 11 parked in WIN_PROBABILITY_FEATURES_V3_CANDIDATES).

The trained artifact is COMMITTED to the database (inactive, exactly like a real "Train"
click) so it shows up in win_probability_status / MLModelsPage for review. It is not
activated -- that is a separate, deliberate step (activate_win_probability), especially
since quality_gate_passed may fail and require force=True.

After training, runs the same coefficient-sign diagnostics as before
(diagnose_feature_matrix) so a wrong-signed or unstable coefficient among the remaining
11 features is visible immediately, and reports whether removing the 6 dead/duplicate
columns actually closed any of the gap against matchup_v1 found by
scripts/compare_v1_v3_trained_models.py.

Run with: DEBUG=false .venv/bin/python scripts/train_v3_candidate_model.py
"""
import asyncio

from cs2eye.analytics.win_probability import temporal_split
from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3, WIN_PROBABILITY_FEATURES_V3
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.prediction import WinProbabilityModelArtifact
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.win_probability_feature_diagnostics_service import diagnose_feature_matrix
from cs2eye.services.win_probability_service import train_win_probability


async def main():
    print(f"feature set (matchup_features_v3): {len(WIN_PROBABILITY_FEATURES_V3)} features")
    print(WIN_PROBABILITY_FEATURES_V3)

    async with AsyncSessionLocal() as session:
        result = await train_win_probability(session, "pre_veto", WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3)
        await session.commit()
        artifact_id = result["artifact_id"]

    async with AsyncSessionLocal() as session:
        committed_artifact = (await session.get(WinProbabilityModelArtifact, artifact_id)).artifact

    print(f"\ntrained and committed: artifact_id={artifact_id} model_version={result['model_version']}")
    print(f"dataset: {result['coverage']['eligible']} eligible / {result['coverage']['total_series']} total "
          f"(coverage {result['coverage']['coverage']:.2%})")
    print(f"split: train={result['split']['training_series']} validation={result['split']['validation_series']} "
          f"test={result['split']['test_series']}")

    test = result["metrics"]["test"]
    print(f"\n{'':<28}{'brier':>9}{'log_loss':>11}{'roc_auc':>10}{'accuracy':>10}")
    for name, key in (("50/50 baseline", "neutral_50"), ("team_strength only", "team_strength"),
                       ("matchup_score only", "matchup_score")):
        m = result["baselines"][key]
        print(f"{name:<28}{m['brier_score']:>9.4f}{m['log_loss']:>11.4f}"
              f"{('-' if m['roc_auc'] is None else round(m['roc_auc'], 4)):>10}{m['accuracy']:>10.4f}")
    print(f"{'v3 candidate (11 features)':<28}{test['brier_score']:>9.4f}{test['log_loss']:>11.4f}"
          f"{('-' if test['roc_auc'] is None else round(test['roc_auc'], 4)):>10}{test['accuracy']:>10.4f}")

    print(f"\nquality_gate_passed: {result['quality_gate_passed']}")

    print("\n--- coefficient sign diagnostics (train split, bootstrap sign stability) ---")
    async with AsyncSessionLocal() as session:
        rows, _ = await AnalyticsAsOfService(session).build_dataset_v3("pre_veto")
    train, _, _ = temporal_split(rows)
    diagnostics = diagnose_feature_matrix([x.features for x in train], [x.target for x in train],
                                           committed_artifact, feature_names=WIN_PROBABILITY_FEATURES_V3)
    header = f"{'feature':<38}{'coef':>9}{'sign':>10}{'expected':>10}{'status':>26}{'sign_rate':>11}"
    print(header)
    flagged = []
    for item in diagnostics["features"]:
        rate = item["bootstrap"]["expected_sign_rate"]
        rate_str = "-" if rate is None else f"{rate:.2f}"
        print(f"{item['feature']:<38}{item['coefficient']:>9.4f}{item['coefficient_sign']:>10}"
              f"{item['expected_direction']:>10}{item['diagnostic_status']:>26}{rate_str:>11}")
        if item["diagnostic_status"] not in ("stable", "weak_signal"):
            flagged.append(item["feature"])

    print(f"\nflagged features (not stable/weak_signal): {flagged or 'none'}")
    if diagnostics["redundancy_candidates"]:
        print("\nredundancy candidates (|corr| >= 0.70):")
        for item in diagnostics["redundancy_candidates"]:
            print(f"  {item['features']} corr={item['correlation']:.3f} ({item['level']})")
    else:
        print("\nno high-correlation redundancy candidates among the 11 features.")

    print(f"\nverdict: quality gate {'PASSED' if result['quality_gate_passed'] else 'FAILED'}; "
          f"{len(flagged)} feature(s) flagged for sign/stability review. "
          f"Candidate artifact_id={artifact_id} is committed but NOT activated.")


if __name__ == "__main__":
    asyncio.run(main())
