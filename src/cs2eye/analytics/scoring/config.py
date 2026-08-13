from dataclasses import dataclass


SCORING_MODEL_VERSION = "v2"
PLAYER_STRENGTH_MODEL_VERSION = "v2.1"
NEUTRAL_SCORE = 50.0


@dataclass(frozen=True)
class NormalizationRule:
    min_value: float
    neutral_value: float
    max_value: float
    source: str = "экспертная базовая линия / временная нормализация"


# Временные экспертные ориентиры. После накопления репрезентативной истории их
# следует заменить эмпирическими распределениями лиги.
NORMALIZATION_RULES = {
    "internal_rating": NormalizationRule(3.0, 6.0, 9.0),
    "bo3_rating": NormalizationRule(4.0, 6.0, 8.0),
    "rating_delta": NormalizationRule(-2.0, 0.0, 2.0),
    "map_rate_percent": NormalizationRule(25.0, 50.0, 75.0),
    "round_rate_percent": NormalizationRule(40.0, 50.0, 60.0),
    "roster_days": NormalizationRule(0.0, 45.0, 180.0),
    "roster_maps": NormalizationRule(0.0, 10.0, 40.0),
}

PLAYER_WEIGHTS = {
    "internal_rating": .25, "bo3_rating": .20, "round_swing": .10,
    "top15_performance": .15, "top16_30_performance": .10,
    "recent_form": .15, "role_performance": .05,
}
TEAM_WEIGHTS = {
    "roster_quality": .45, "team_performance": .20,
    "strong_opponents": .15, "recent_form": .10,
    "roster_stability": .10,
}
MAP_WEIGHTS = {
    "overall_performance": .45, "recent_form": .25,
    "strong_opponents": .20, "side_strength": .10,
}


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def normalize(value: float, rule_key: str) -> float:
    """Piecewise-linear 0..100 mapping with an explicit neutral midpoint."""
    rule = NORMALIZATION_RULES[rule_key]
    if value <= rule.neutral_value:
        span = rule.neutral_value - rule.min_value
        result = 50.0 if span == 0 else (value - rule.min_value) / span * 50.0
    else:
        span = rule.max_value - rule.neutral_value
        result = 50.0 if span == 0 else 50.0 + (value - rule.neutral_value) / span * 50.0
    return clamp(result, 0.0, 100.0)
