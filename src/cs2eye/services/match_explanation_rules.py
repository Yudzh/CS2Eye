"""Centralized, transparent rules for Deterministic Explanation Layer v1."""

MAX_ADVANTAGES = 5
MAX_COUNTER_ARGUMENTS = 5
MAX_CONTRADICTIONS = 3
MAX_RISKS = 5

MIN_SIGNAL_RELIABILITY = 0.35
MIN_MAP_RELIABILITY = 0.40
MIN_H2H_RELIABILITY = 0.45
MIN_H2H_SAMPLE = 2
MIN_FACTOR_DISTANCE = 3.0
MIN_FORM_SAMPLE = 3
MIN_MAP_SAMPLE = 3

ML_ADVANTAGE_SMALL_DELTA = 0.0
ML_ADVANTAGE_MODERATE_DELTA = 0.20
ML_ADVANTAGE_CLEAR_DELTA = 0.35

CONFIDENCE_HIGH = 0.80
CONFIDENCE_MEDIUM = 0.60

MATCHUP_NEUTRAL_MIN = 47.0
MATCHUP_NEUTRAL_MAX = 53.0


def probability_advantage(a: float | None, b: float | None) -> str:
    if a is None or b is None or a == b:
        return "none"
    delta = abs(a - b)
    if delta >= ML_ADVANTAGE_CLEAR_DELTA:
        return "clear"
    if delta >= ML_ADVANTAGE_MODERATE_DELTA:
        return "moderate"
    return "small"


def score_side(team_a_score: float | None, *, neutral=True) -> str | None:
    if team_a_score is None:
        return None
    if neutral:
        if team_a_score > MATCHUP_NEUTRAL_MAX:
            return "team_a"
        if team_a_score < MATCHUP_NEUTRAL_MIN:
            return "team_b"
        return None
    if team_a_score == 50:
        return None
    return "team_a" if team_a_score > 50 else "team_b"


def signal_strength(distance: float) -> str:
    return "strong" if distance >= 15 else "moderate" if distance >= 8 else "small"


def confidence_level(reliability: float, quality: str, *, conflict: bool) -> str:
    if quality == "insufficient":
        return "insufficient"
    adjusted = reliability
    if quality == "weak":
        adjusted = min(adjusted, 0.44)
    elif quality == "partial":
        adjusted = min(adjusted, 0.69)
    if conflict:
        adjusted -= 0.10
    if adjusted >= CONFIDENCE_HIGH:
        return "high"
    if adjusted >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"
