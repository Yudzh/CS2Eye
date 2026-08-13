from dataclasses import dataclass, replace
from typing import Any

from .config import NEUTRAL_SCORE, SCORING_MODEL_VERSION, clamp


@dataclass(frozen=True)
class FactorInput:
    key: str
    label: str
    raw_value: Any
    normalized_score: float | None
    weight: float
    sample_size: int | None = None
    confidence: float | None = None
    reason: str | None = None
    available: bool = True
    reference_value: float | None = None
    reference_source: str | None = None


@dataclass(frozen=True)
class ScoringFactor:
    key: str
    label: str
    raw_value: Any
    normalized_score: float | None
    weight: float
    effective_weight: float
    impact: float
    sample_size: int | None
    confidence: float | None
    reason: str | None
    available: bool
    reference_value: float | None
    reference_source: str | None


@dataclass(frozen=True)
class ScoringBreakdown:
    model_version: str
    raw_score: float
    reliability: float
    confidence_adjustment: float
    final_score: float
    factors: list[ScoringFactor]


def score_factors(inputs: list[FactorInput], reliability: float) -> ScoringBreakdown:
    reliability = clamp(reliability, 0.0, 1.0)
    available_weight = sum(
        item.weight for item in inputs
        if item.available and item.normalized_score is not None
    )
    factors: list[ScoringFactor] = []
    for item in inputs:
        available = item.available and item.normalized_score is not None
        effective = item.weight / available_weight if available_weight and available else 0.0
        score = clamp(float(item.normalized_score), 0.0, 100.0) if available else None
        impact = (score - NEUTRAL_SCORE) * effective if score is not None else 0.0
        factors.append(ScoringFactor(
            key=item.key, label=item.label, raw_value=item.raw_value,
            normalized_score=round(score, 2) if score is not None else None,
            weight=item.weight, effective_weight=round(effective, 6),
            impact=round(impact, 2), sample_size=item.sample_size,
            confidence=(round(clamp(item.confidence, 0.0, 1.0), 4)
                        if item.confidence is not None else None),
            reason=item.reason, available=available,
            reference_value=item.reference_value,
            reference_source=item.reference_source,
        ))
    raw = clamp(NEUTRAL_SCORE + sum(item.impact for item in factors), 0.0, 100.0)
    final = clamp(NEUTRAL_SCORE + (raw - NEUTRAL_SCORE) * reliability, 0.0, 100.0)
    return ScoringBreakdown(
        SCORING_MODEL_VERSION, round(raw, 2), round(reliability, 4),
        round(final - raw, 2), round(final, 2), factors,
    )


def sample_reliability(sample_size: int, prior_size: float = 10.0) -> float:
    return clamp(sample_size / (sample_size + prior_size), 0.0, 1.0)


def regress_rate(
    numerator: int, denominator: int, *, reference_rate: float = .5,
    prior_size: float = 10.0,
) -> tuple[float, float]:
    if denominator <= 0:
        return reference_rate, 0.0
    reliability = sample_reliability(denominator, prior_size)
    observed = clamp(numerator / denominator, 0.0, 1.0)
    return (
        reliability * observed + (1.0 - reliability) * reference_rate,
        reliability,
    )
