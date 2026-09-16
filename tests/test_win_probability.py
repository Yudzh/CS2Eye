from dataclasses import dataclass
from datetime import date

import pytest

from cs2eye.analytics.win_probability import (
    WinProbabilityModel,
    probability_metrics,
    temporal_split,
)
from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURES
from cs2eye.services.win_probability_service import _feature_vector, explain_prediction


def features(value: float = 0.0) -> dict[str, float]:
    return {key: value for key in WIN_PROBABILITY_FEATURES}


def training_rows() -> tuple[list[dict[str, float]], list[int]]:
    rows=[];targets=[]
    for index in range(40):
        value=(index-20)/20
        row=features()
        row["team_strength_difference"]=value
        row["matchup_score_centered"]=value*.8
        rows.append(row);targets.append(int(value>0))
    return rows,targets


def test_probability_metrics_include_calibration() -> None:
    result=probability_metrics([.1,.4,.6,.9],[0,0,1,1])
    assert 0<=result["brier_score"]<=1
    assert result["log_loss"]>0
    assert 0<=result["ece"]<=1
    assert result["roc_auc"]==1
    assert result["calibration_bins"]


def test_probability_metrics_reject_mismatched_arrays() -> None:
    with pytest.raises(ValueError):probability_metrics([.5],[])


def test_model_probability_is_bounded_and_symmetric() -> None:
    rows,targets=training_rows();model=WinProbabilityModel.train(rows,targets)
    positive=features();positive["team_strength_difference"]=.8;positive["matchup_score_centered"]=.6
    negative={key:-value for key,value in positive.items()}
    p=model.predict_symmetric([positive])[0];reverse=model.predict_symmetric([negative])[0]
    assert 0<p<1
    assert p==pytest.approx(1-reverse)
    assert p>.5


def test_neutral_features_are_exactly_neutral_after_symmetry() -> None:
    rows,targets=training_rows();model=WinProbabilityModel.train(rows,targets)
    assert model.predict_symmetric([features()])[0]==pytest.approx(.5)


def test_prediction_explanation_ranks_local_probability_impacts() -> None:
    rows,targets=training_rows();model=WinProbabilityModel.train(rows,targets)
    current=features();current["team_strength_difference"]=.8;current["matchup_score_centered"]=.6
    probability=model.predict_symmetric([current])[0]
    result=explain_prediction(model,current,probability)
    assert result["neutral_probability"]==pytest.approx(.5)
    assert result["top_factors"][0]["impact_percentage_points"]>0
    assert result["top_factors"][0]["favors"]=="team_a"


@dataclass(frozen=True)
class Row:
    match_date: date
    series_id: int


def test_temporal_split_is_chronological() -> None:
    rows=[Row(date(2026,1,index),index) for index in range(1,29)]
    train,validation,test=temporal_split(list(reversed(rows)))
    assert train[-1].match_date<=validation[0].match_date
    assert validation[-1].match_date<=test[0].match_date
    assert not ({x.series_id for x in train}&{x.series_id for x in test})


def test_temporal_split_requires_meaningful_holdout() -> None:
    with pytest.raises(ValueError):temporal_split([Row(date(2026,1,1),1)]*10)


def test_feature_vector_keeps_matchup_and_probability_separate() -> None:
    matchup={
        "team_a":{"score":60},"raw_score":70,"reliability":.5,
        "factors":[
            {"key":"team_strength","score":65,"confidence":1.0},
            {"key":"map_veto","score":55,"confidence":1.0},
            {"key":"current_roster_form","score":52,"confidence":1.0},
            {"key":"tactical_matchup","score":58,"confidence":.3},
            {"key":"h2h","score":None,"confidence":1.0},
            {"key":"leadership_context","score":51,"confidence":1.0},
        ],
    }
    result=_feature_vector(matchup,"bo3",.25)
    assert result["matchup_score_centered"]==pytest.approx(.2)
    assert result["raw_matchup_centered"]==pytest.approx(.4)
    assert result["team_strength_difference"]==pytest.approx(.3)
    assert result["h2h_advantage"]==0
    # tactical_matchup's low confidence (.3) must discount the feature by the same
    # factor, not just the matchup engine's own contribution to the matchup score --
    # otherwise ML sees a sparse-data factor at full strength while matchup itself
    # has already discounted it toward neutral.
    assert result["tactical_advantage"]==pytest.approx((58-50)/50*.3)
