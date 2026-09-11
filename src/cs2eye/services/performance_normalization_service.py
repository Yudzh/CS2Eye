from __future__ import annotations

class PerformanceNormalizationService:
    """Versioned population normalization shared by V3 performance models."""

    VERSION = "performance_normalization.v2_percentile"

    @staticmethod
    def score(value: float | None, population: list[float], *, inverse: bool = False) -> float | None:
        if value is None or not population:
            return None
        ordered = sorted(float(item) for item in population)
        if len(ordered) == 1:
            normalized = 50.0
        else:
            below = sum(item < value for item in ordered)
            equal = sum(item == value for item in ordered)
            # Mid-rank empirical percentile: population median is approximately
            # 50, distribution tails approach 0/100, and no arbitrary V2 anchors
            # or confidence shrinkage enter the score.
            rank = below + max(0.0, (equal - 1) / 2)
            normalized = 100.0 * rank / (len(ordered) - 1)
            normalized = max(0.0, min(100.0, normalized))
        return round(100.0 - normalized if inverse else normalized, 2)
