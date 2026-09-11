from __future__ import annotations

from math import exp

from cs2eye.analytics.team_form_v3_config import (
    ACTUAL_PERFORMANCE_WEIGHTS, EVENT_CONTRIBUTION_SCALE,
    EXPECTATION_LOGISTIC_SCALE, EXPECTED_ROUND_PERFORMANCE_RANGE,
    FORM_DELTA_LIMIT,
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class PerformanceVsExpectationService:
    """Turn one completed series into exactly one form signal."""

    @staticmethod
    def expected_win_probability(own_strength: float, opponent_strength: float) -> float:
        return 1.0/(1.0+exp(-(own_strength-opponent_strength)/EXPECTATION_LOGISTIC_SCALE))

    def evaluate(self, *, own_strength: float, opponent_strength: float,
                 won: bool, round_diff: int, maps: int, bo_format: str) -> dict:
        expected = self.expected_win_probability(own_strength, opponent_strength)
        normalized_round_diff = clamp(round_diff/max(13, 13*max(1, maps)), -1.0, 1.0)
        round_performance = 0.5+0.5*normalized_round_diff
        expected_round_performance = (
            0.5+EXPECTED_ROUND_PERFORMANCE_RANGE*(2.0*expected-1.0)
        )
        actual = (ACTUAL_PERFORMANCE_WEIGHTS["result"]*float(won) +
                  ACTUAL_PERFORMANCE_WEIGHTS["rounds"]*round_performance)
        expected_performance = (
            ACTUAL_PERFORMANCE_WEIGHTS["result"]*expected +
            ACTUAL_PERFORMANCE_WEIGHTS["rounds"]*expected_round_performance
        )
        residual = actual-expected_performance
        contribution = clamp(residual*EVENT_CONTRIBUTION_SCALE,
                             -FORM_DELTA_LIMIT, FORM_DELTA_LIMIT)
        return {"expected": round(expected, 6),
                "expected_performance": round(expected_performance, 6),
                "actual_performance": round(actual, 6),
                "expected_round_performance": round(expected_round_performance, 6),
                "round_performance": round(round_performance, 6),
                "actual_result": "win" if won else "loss",
                "normalized_round_diff": round(normalized_round_diff, 6),
                "performance_vs_expectation": round(residual, 6),
                "form_contribution": round(contribution, 2),
                "bo_format": bo_format, "formula": ACTUAL_PERFORMANCE_WEIGHTS}
