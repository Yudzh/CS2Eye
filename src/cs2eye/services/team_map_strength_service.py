from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping

from cs2eye.models.demo import TeamMapAggregate
from cs2eye.services.team_map_aggregate_service import freshness_label


@dataclass(frozen=True)
class MapStrengthFactor:
    code: str
    label: str
    score: float | None
    configured_weight: float
    effective_weight: float
    impact: float
    explanation: str


@dataclass(frozen=True)
class MapStrengthResult:
    status: str
    map_strength_score: float | None
    performance_score: float | None
    confidence_score: float
    confidence_level: str
    factors: list[MapStrengthFactor]
    warnings: list[str]


COMPONENT_WEIGHTS = {
    "overall_performance": 0.45,
    "recent_form": 0.25,
    "strong_opponents": 0.20,
    "side_strength": 0.10,
}

FACTOR_LABELS = {
    "overall_performance": "Общий результат",
    "recent_form": "Текущая форма",
    "strong_opponents": "Результаты против сильных соперников",
    "side_strength": "Баланс сторон",
    "confidence_adjustment": "Поправка на надёжность",
}


def _number(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def scope_performance(scope: TeamMapAggregate | None) -> float | None:
    if scope is None:
        return None
    map_rate = _number(scope.map_win_rate)
    round_rate = _number(scope.round_win_rate)
    if map_rate is not None and round_rate is not None:
        return _clamp(map_rate * 0.60 + round_rate * 0.40)
    if map_rate is not None:
        return _clamp(map_rate)
    if round_rate is not None:
        return _clamp(round_rate)
    return None


def calculate_map_strength(
    scopes: Mapping[str, TeamMapAggregate],
    today: date | None = None,
) -> MapStrengthResult:
    all_scope = scopes.get("all")
    if all_scope is None:
        return MapStrengthResult(
            status="not_enough_data", map_strength_score=None,
            performance_score=None, confidence_score=0.0,
            confidence_level="not_enough_data", factors=[],
            warnings=["small_sample", "no_matches_against_top_30", "missing_side_data"],
        )

    component_scores: dict[str, float] = {}
    explanations: dict[str, str] = {}

    overall = scope_performance(all_scope)
    if overall is not None:
        component_scores["overall_performance"] = overall
        explanations["overall_performance"] = (
            f"Общий результат {overall:.2f} по {all_scope.maps_played} картам."
        )

    for window in (5, 10, 20):
        scope = scopes.get(f"recent:{window}")
        if scope is None or scope.maps_played < 3:
            continue
        recent = scope_performance(scope)
        if recent is not None:
            component_scores["recent_form"] = recent
            explanations["recent_form"] = (
                f"Форма {recent:.2f}: использовано окно recent:{window}, "
                f"фактическая выборка — {scope.maps_played} карт."
            )
        break

    opponent_parts: list[tuple[float, float, str, int]] = []
    for key, multiplier, label in (
        ("rank:top_15", 1.5, "Top-15"),
        ("rank:top_16_30", 1.0, "Top 16–30"),
    ):
        scope = scopes.get(key)
        if scope is None or scope.maps_played <= 0:
            continue
        score = scope_performance(scope)
        if score is not None:
            opponent_parts.append(
                (score, min(scope.maps_played, 5) * multiplier, label, scope.maps_played)
            )
    if opponent_parts:
        total_weight = sum(part[1] for part in opponent_parts)
        strong = sum(part[0] * part[1] for part in opponent_parts) / total_weight
        component_scores["strong_opponents"] = strong
        details = ", ".join(
            f"{label}: {maps} карт, score {score:.2f}, вес {weight:g}"
            for score, weight, label, maps in opponent_parts
        )
        explanations["strong_opponents"] = (
            f"Средневзвешенный результат против Top-30 — {strong:.2f} ({details})."
        )

    ct_rate = _number(all_scope.ct_win_rate)
    t_rate = _number(all_scope.t_win_rate)
    if ct_rate is not None and t_rate is not None:
        weak_side, strong_side = min(ct_rate, t_rate), max(ct_rate, t_rate)
        side = _clamp(weak_side * 0.65 + strong_side * 0.35)
        component_scores["side_strength"] = side
        explanations["side_strength"] = (
            f"Слабая сторона {weak_side:.2f} учитывается с весом 65%, "
            f"сильная {strong_side:.2f} — с весом 35%; результат {side:.2f}."
        )
    elif ct_rate is not None or t_rate is not None:
        side = ct_rate if ct_rate is not None else t_rate
        assert side is not None
        component_scores["side_strength"] = _clamp(side)
        side_name = "CT" if ct_rate is not None else "T"
        explanations["side_strength"] = (
            f"Доступна только сторона {side_name}; использован её winrate {side:.2f}."
        )

    available_weight = sum(COMPONENT_WEIGHTS[code] for code in component_scores)
    performance = (
        sum(component_scores[code] * COMPONENT_WEIGHTS[code] for code in component_scores)
        / available_weight
        if available_weight else None
    )
    if performance is not None:
        performance = _clamp(performance)

    top_15_maps = scopes.get("rank:top_15").maps_played if scopes.get("rank:top_15") else 0
    top_16_30_maps = scopes.get("rank:top_16_30").maps_played if scopes.get("rank:top_16_30") else 0
    ranked_maps = top_15_maps + top_16_30_maps
    opponent_coverage = min(100.0, ranked_maps * 10.0)
    side_rounds = min(all_scope.ct_rounds_played, all_scope.t_rounds_played)
    side_coverage = min(100.0, side_rounds / 24.0 * 100.0)
    confidence = _clamp(
        (_number(all_scope.sample_size_score) or 0.0) * 0.50
        + (_number(all_scope.freshness_score) or 0.0) * 0.25
        + opponent_coverage * 0.15
        + side_coverage * 0.10
    )

    if all_scope.maps_played < 3:
        status = "not_enough_data"
        confidence_level = "not_enough_data"
        strength = None
    else:
        status = "available"
        confidence_level = (
            "low_confidence" if confidence < 40
            else "medium_confidence" if confidence < 70
            else "high_confidence"
        )
        reliability_factor = 0.5 + 0.5 * confidence / 100.0
        strength = (
            _clamp(50.0 + (performance - 50.0) * reliability_factor)
            if performance is not None else None
        )

    factors = []
    for code, score in component_scores.items():
        effective_weight = COMPONENT_WEIGHTS[code] / available_weight
        impact = (score - 50.0) * effective_weight
        factors.append(MapStrengthFactor(
            code=code, label=FACTOR_LABELS[code], score=score,
            configured_weight=COMPONENT_WEIGHTS[code],
            effective_weight=effective_weight, impact=impact,
            explanation=(
                f"{explanations[code]} Нормализованный вес "
                f"{effective_weight * 100:.2f}% даёт влияние {impact:+.2f} пункта."
            ),
        ))
    if performance is not None:
        adjustment = (strength - performance) if strength is not None else 0.0
        factors.append(MapStrengthFactor(
            code="confidence_adjustment",
            label=FACTOR_LABELS["confidence_adjustment"],
            score=confidence, configured_weight=0.0, effective_weight=0.0,
            impact=adjustment,
            explanation=(
                f"Надёжность {confidence:.2f}/100 стягивает оценку к нейтральным 50; "
                + (f"поправка {adjustment:+.2f} пункта." if strength is not None
                   else "числовая сила не публикуется до трёх карт.")
            ),
        ))

    warnings: list[str] = []
    if 3 <= all_scope.maps_played <= 4:
        warnings.append("small_sample")
    label = freshness_label(all_scope.last_match_date, today or date.today())
    if label == "stale":
        warnings.append("stale_data")
    elif label == "very_stale":
        warnings.append("very_stale_data")
    if ranked_maps == 0:
        warnings.append("no_matches_against_top_30")
    if all_scope.ct_rounds_played < 12:
        warnings.append("low_ct_sample")
    if all_scope.t_rounds_played < 12:
        warnings.append("low_t_sample")
    if ct_rate is None or t_rate is None:
        warnings.append("missing_side_data")

    return MapStrengthResult(
        status=status, map_strength_score=strength,
        performance_score=performance, confidence_score=confidence,
        confidence_level=confidence_level, factors=factors, warnings=warnings,
    )
