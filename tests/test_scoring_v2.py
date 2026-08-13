import pytest

from cs2eye.analytics.scoring.core import (
    FactorInput, regress_rate, sample_reliability, score_factors,
)


def factor(key: str, score: float | None, weight: float, available: bool = True):
    return FactorInput(key, key, score, score, weight, available=available)


@pytest.mark.parametrize(("score", "expected"), [(50, 0), (70, 2), (30, -2)])
def test_neutral_impact_formula(score: float, expected: float) -> None:
    result = score_factors([factor("x", score, .10), factor("neutral", 50, .90)], 1)
    assert result.factors[0].impact == expected
    direct = (score - 50) * .10
    assert direct == expected


def test_impacts_form_raw_and_reliability_forms_final() -> None:
    result = score_factors([factor("a", 70, .5), factor("b", 30, .5)], .25)
    assert result.raw_score == 50
    assert result.final_score == 50
    high = score_factors([factor("a", 90, 1)], .25)
    assert high.raw_score == 90
    assert high.final_score == 60
    assert high.confidence_adjustment == -30


def test_clamps_scores_and_reliability() -> None:
    assert score_factors([factor("x", 200, 1)], 2).final_score == 100
    assert score_factors([factor("x", -10, 1)], -2).final_score == 50


def test_missing_factor_is_not_zero_and_weights_redistribute() -> None:
    result = score_factors([
        factor("present", 70, .30), factor("missing", None, .70, False),
    ], 1)
    assert result.factors[1].normalized_score is None
    assert result.factors[1].impact == 0
    assert result.factors[0].effective_weight == 1
    assert sum(item.effective_weight for item in result.factors) == 1


def test_regression_to_mean_depends_on_sample() -> None:
    small, small_r = regress_rate(7, 10, reference_rate=.5, prior_size=10)
    large, large_r = regress_rate(70, 100, reference_rate=.5, prior_size=10)
    assert .5 < small < large < .7
    assert small_r < large_r
    assert sample_reliability(1000, 10) > .99
