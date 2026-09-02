import math

import pytest

from cs2eye.services.prediction_history_evaluation_service import PredictionHistoryEvaluationService


def item(ts, matchup, ml, actual, p=.8, *, source="pre_match", version="v1"):
    comparison = PredictionHistoryEvaluationService.comparison([ts, matchup, ml])
    def prediction(winner, value=None):
        return {"predicted_winner_id": winner, "correct": None if winner is None else winner == actual,
                "team_a_value": value}
    return {"source": source, "completed": True, "actual_winner_id": actual,
            "team_a": {"id": 1}, "team_b": {"id": 2},
            "team_strength": prediction(ts), "matchup": prediction(matchup),
            "ml": prediction(ml, p), "comparison": comparison,
            "versions": {"team_strength": "v2", "matchup": "matchup_v1", "ml": version,
                         "ml_feature_schema": "features_v2"}}


@pytest.mark.parametrize(("predictions", "expected"), [
    ((1, 1, 1), "consensus_3_3"), ((2, 1, 1), "team_strength_dissent"),
    ((1, 2, 1), "matchup_dissent"), ((1, 1, 2), "ml_dissent"),
    ((1, 1, None), "incomplete"),
])
def test_comparison_classification(predictions, expected):
    assert PredictionHistoryEvaluationService.comparison(list(predictions))["type"] == expected


def test_exact_aggregate_probabilistic_calibration_and_versions():
    rows = [
        item(1, 1, 1, 1, .8, version="v1"),
        item(1, 1, 2, 2, .8, version="v1"),
        item(1, 2, 1, 1, .6, version="v2"),
        item(2, 1, 1, 2, .6, version="v2"),
        item(2, 2, None, 1, .5, version="v2"),
        item(2, 2, 2, 2, .52, source="retrospective", version="v1"),
    ]
    stats = PredictionHistoryEvaluationService().evaluate(rows)
    assert stats["team_strength"] == {"correct": 3, "total": 5, "accuracy": .6}
    assert stats["matchup"] == {"correct": 1, "total": 5, "accuracy": .2}
    assert stats["ml"] == {"correct": 3, "total": 4, "accuracy": .75}
    assert stats["consensus_3_3"] == {"correct": 1, "total": 1, "accuracy": 1}
    assert stats["conflicts"]["majority_accuracy"] == pytest.approx(1 / 3)
    assert stats["conflicts"]["dissent_accuracy"] == pytest.approx(2 / 3)
    assert stats["dissent"]["ml"]["dissent_accuracy"] == 1
    assert stats["ml_quality"]["brier_score"] == pytest.approx((.04 + .64 + .16 + .36) / 4)
    expected_log_loss = sum((-math.log(.8), -math.log(.2), -math.log(.6), -math.log(.4))) / 4
    assert stats["ml_quality"]["log_loss"] == pytest.approx(expected_log_loss)
    assert next(x for x in stats["calibration"] if x["range"] == "60-65")["samples"] == 2
    versions = {x["model_version"]: x for x in stats["by_version"]["ml"]}
    assert versions["v1"]["accuracy"] == 1
    assert versions["v2"]["accuracy"] == .5
    assert stats["snapshot_counts"]["retrospective"] == 1
