"""Train/serve parity for the win-probability feature vector.

Training (AnalyticsAsOfService.features, used by train_win_probability /
backtest_win_probability) and live serving (win_probability_service's
_feature_vector, used by predict_win_probability for the current day) are two
independently maintained implementations of the same feature transform. They
were built to compute identical values from the same underlying matchup
factors/form context, but nothing enforced that beyond code review — this
test pins the contract so a future edit to one without the other is caught,
instead of silently producing a model that predicts on features it was never
trained on.
"""

import pytest

from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURES
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.win_probability_service import _feature_vector


def _context(*, team_a_score=58.0, raw_score=55.0, reliability=.6, factors, form_context=None):
    return {
        "team_a": {"score": team_a_score}, "raw_score": raw_score, "reliability": reliability,
        "factors": factors, **({"form_context": form_context} if form_context else {}),
    }


def _factors(confidence=1.0, **scores):
    return [{"key": key, "score": score, "confidence": confidence} for key, score in scores.items()]


@pytest.mark.parametrize("factors", [
    _factors(team_strength=65, map_veto=55, current_roster_form=52, tactical_matchup=58,
             h2h=40, leadership_context=80),
    # A real score of exactly 0 is a legitimate, non-missing value: a falsy-vs-None
    # bug (`x or 50` instead of an is-None check) previously made training silently
    # treat it as "missing" and round it up to neutral (50) instead of -1.0.
    _factors(team_strength=0, map_veto=0, current_roster_form=0, tactical_matchup=0, h2h=0),
    # A factor absent entirely (not even in the list) must also read as neutral,
    # matching a factor present but with score=None.
    _factors(team_strength=70),
    # Reliability weighting (see centered() in both implementations) must be applied
    # identically -- a low, non-1.0 confidence must discount training and live serving
    # by the same amount, not just a full-confidence factor.
    _factors(confidence=.3, team_strength=65, map_veto=55, tactical_matchup=58, h2h=40),
])
def test_features_match_between_training_and_live_serving(factors):
    context = _context(factors=factors, form_context={
        "team_a_form_context": {
            "tournament_form_score": 62, "recent_60d_adjusted_form_score": 58,
            "strength_of_schedule_score": 55, "performance_vs_expectation_score": 3,
        },
        "team_b_form_context": {
            "tournament_form_score": 48, "recent_60d_adjusted_form_score": 51,
            "strength_of_schedule_score": 49, "performance_vs_expectation_score": -2,
        },
    })
    training = AnalyticsAsOfService.features(context, "bo3", {}, None, 1, 2)
    live = _feature_vector(context, "bo3", ranking_advantage=0.0)
    for key in WIN_PROBABILITY_FEATURES:
        assert training[key] == pytest.approx(live[key]), f"{key} diverged: train={training[key]} serve={live[key]}"
