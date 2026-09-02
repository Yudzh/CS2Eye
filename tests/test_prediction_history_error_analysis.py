import pytest

from cs2eye.services.prediction_history_error_analysis_service import PredictionHistoryErrorAnalysisService


def prediction(winner, a, b, actual):
    return {"predicted_winner_id": winner, "team_a_value": a, "team_b_value": b,
            "correct": None if winner is None else winner == actual}


def analyzed(*, actual=2, source="pre_match", factors=True, ml_probability=.72):
    item = {"source": source, "completed": True, "actual_winner_id": actual,
            "team_a": {"id": 1}, "team_b": {"id": 2},
            "versions": {"matchup": "matchup_v1"},
            "team_strength": prediction(1, 56, 44, actual),
            "matchup": prediction(1, 55, 45, actual),
            "ml": prediction(1, ml_probability, 1 - ml_probability, actual)}
    snapshot = None if not factors else {"factors": {
        "map_veto": {"label": "Veto", "team_a_score": 60, "team_b_score": 40,
                     "weight": .3, "effective_weight": .3, "reliability": .2,
                     "sample": 2, "available": True, "raw_contribution": 3, "contribution": 2.5},
        "team_strength": {"label": "Strength", "team_a_score": 56, "team_b_score": 44,
                          "weight": .23, "effective_weight": .23, "reliability": .6,
                          "sample": 10, "available": True, "raw_contribution": 1.2, "contribution": 1.2},
        "form_context": {"label": "Form", "team_a_score": 45, "team_b_score": 55,
                         "weight": .15, "effective_weight": .15, "reliability": .9,
                         "sample": 8, "available": True, "raw_contribution": -.7, "contribution": -.7},
    }}
    item["error_analysis"] = PredictionHistoryErrorAnalysisService.analyze_item(item, snapshot)
    return item


def test_strongest_driver_ignores_factor_pointing_to_actual_winner_and_margin_is_full_difference():
    item = analyzed()
    matchup = item["error_analysis"]["matchup"]
    assert matchup["margin"] == 10
    assert matchup["strongest_driver"]["factor"] == "map_veto"
    assert [x["factor"] for x in matchup["error_drivers"]] == ["map_veto", "team_strength"]
    assert next(x for x in matchup["factors"] if x["factor"] == "form_context")["direction_correct"] is True


def test_factor_quality_reliability_buckets_high_confidence_and_retrospective_exclusion():
    official = analyzed()
    retrospective = analyzed(source="retrospective", actual=1)
    stats = PredictionHistoryErrorAnalysisService().aggregate([official, retrospective])
    veto = stats["matchup_factor_quality"]["map_veto"]
    assert (veto["directional_cases"], veto["direction_correct"], veto["direction_accuracy"]) == (1, 0, 0)
    assert veto["reliability"]["low"] == {"samples": 1, "direction_accuracy": 0}
    assert stats["matchup_factor_quality"]["team_strength"]["reliability"]["medium"]["samples"] == 1
    assert stats["matchup_factor_quality"]["form_context"]["reliability"]["high"]["samples"] == 1
    assert stats["ml_high_confidence_errors"]["65_plus"]["errors"] == 1
    assert stats["ml_high_confidence_errors"]["70_plus"]["errors"] == 1
    assert stats["ml_high_confidence_errors"]["80_plus"]["predictions"] == 0


def test_legacy_snapshot_is_not_available_and_does_not_enter_factor_aggregates():
    item = analyzed(factors=False)
    assert item["error_analysis"]["matchup"]["status"] == "not_available"
    assert PredictionHistoryErrorAnalysisService().aggregate([item])["matchup_factor_quality"] == {}
