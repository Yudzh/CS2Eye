from datetime import date, timedelta
from decimal import Decimal

import pytest

from cs2eye.models.demo import TeamMapAggregate
from cs2eye.services.team_map_strength_service import (
    calculate_map_strength, scope_performance,
)


TODAY = date(2026, 8, 6)


def aggregate(
    scope_key: str = "all", *, maps: int = 10,
    map_rate: float | None = 60, round_rate: float | None = 55,
    ct_rate: float | None = 52, t_rate: float | None = 58,
    ct_rounds: int = 60, t_rounds: int = 60,
    sample: float = 75, freshness: float = 100, age: int = 0,
) -> TeamMapAggregate:
    return TeamMapAggregate(
        team_id=1, aggregation_level="organization", roster_id=None,
        map_name="mirage", scope="all", scope_key=scope_key,
        maps_played=maps, maps_won=maps // 2, maps_lost=maps - maps // 2,
        map_win_rate=Decimal(str(map_rate)) if map_rate is not None else None,
        rounds_played=ct_rounds + t_rounds, rounds_won=60, rounds_lost=60,
        round_win_rate=Decimal(str(round_rate)) if round_rate is not None else None,
        ct_rounds_played=ct_rounds, ct_rounds_won=30, ct_rounds_lost=max(0, ct_rounds - 30),
        ct_win_rate=Decimal(str(ct_rate)) if ct_rate is not None else None,
        t_rounds_played=t_rounds, t_rounds_won=30, t_rounds_lost=max(0, t_rounds - 30),
        t_win_rate=Decimal(str(t_rate)) if t_rate is not None else None,
        overtime_maps=0, overtime_rounds_played=0, overtime_rounds_won=0,
        sample_size_score=Decimal(str(sample)), freshness_score=Decimal(str(freshness)),
        first_match_date=TODAY - timedelta(days=age + 30),
        last_match_date=TODAY - timedelta(days=age), calculated_at=None,
    )


def factor(result, code: str):
    return next(item for item in result.factors if item.code == code)


def test_scope_performance_and_missing_metric() -> None:
    assert scope_performance(aggregate(map_rate=70, round_rate=50)) == 62
    assert scope_performance(aggregate(map_rate=None, round_rate=57)) == 57
    assert scope_performance(aggregate(map_rate=63, round_rate=None)) == 63
    assert scope_performance(aggregate(map_rate=None, round_rate=None)) is None


def test_exact_component_weights() -> None:
    scopes = {
        "all": aggregate(map_rate=60, round_rate=60),
        "recent:5": aggregate("recent:5", maps=5, map_rate=70, round_rate=70),
        "rank:top_15": aggregate("rank:top_15", maps=5, map_rate=80, round_rate=80),
    }
    result = calculate_map_strength(scopes, TODAY)
    assert factor(result, "overall_performance").configured_weight == .45
    assert factor(result, "recent_form").configured_weight == .25
    assert factor(result, "strong_opponents").configured_weight == .20
    assert factor(result, "side_strength").configured_weight == .10
    assert result.performance_score == pytest.approx(65.91)


def test_missing_components_normalize_remaining_weights() -> None:
    result = calculate_map_strength({
        "all": aggregate(map_rate=60, round_rate=60, ct_rate=None, t_rate=None),
    }, TODAY)
    overall = factor(result, "overall_performance")
    assert overall.effective_weight == 1
    assert result.performance_score == 60


@pytest.mark.parametrize(("available", "expected"), [
    ((5, 10, 20), 5), ((10, 20), 10), ((20,), 20),
])
def test_recent_window_priority(available: tuple[int, ...], expected: int) -> None:
    scopes = {"all": aggregate()}
    for window in available:
        scopes[f"recent:{window}"] = aggregate(f"recent:{window}", maps=3, map_rate=window, round_rate=window)
    result = calculate_map_strength(scopes, TODAY)
    recent = factor(result, "recent_form")
    assert recent.score == expected
    assert f"recent:{expected}" in recent.explanation


def test_recent_window_requires_three_actual_maps() -> None:
    result = calculate_map_strength({
        "all": aggregate(),
        "recent:5": aggregate("recent:5", maps=2, map_rate=99, round_rate=99),
        "recent:10": aggregate("recent:10", maps=4, map_rate=61, round_rate=61),
    }, TODAY)
    assert factor(result, "recent_form").score == 61


def test_strong_opponents_and_top15_weight() -> None:
    result = calculate_map_strength({
        "all": aggregate(),
        "rank:top_15": aggregate("rank:top_15", maps=5, map_rate=80, round_rate=80),
        "rank:top_16_30": aggregate("rank:top_16_30", maps=5, map_rate=50, round_rate=50),
    }, TODAY)
    assert factor(result, "strong_opponents").score == pytest.approx(68)


def test_side_strength_emphasizes_weak_side() -> None:
    result = calculate_map_strength({"all": aggregate(ct_rate=80, t_rate=40)}, TODAY)
    assert factor(result, "side_strength").score == 54


def test_confidence_formula_without_premature_rounding() -> None:
    result = calculate_map_strength({
        "all": aggregate(sample=77.7777, freshness=66.6666, ct_rounds=17, t_rounds=31),
        "rank:top_15": aggregate("rank:top_15", maps=2),
        "rank:top_16_30": aggregate("rank:top_16_30", maps=3),
    }, TODAY)
    expected = 77.7777 * .5 + 66.6666 * .25 + 50 * .15 + (17 / 24 * 100) * .10
    assert result.confidence_score == pytest.approx(expected)


@pytest.mark.parametrize(("confidence", "level"), [
    (39.999, "low_confidence"), (40, "medium_confidence"),
    (69.999, "medium_confidence"), (70, "high_confidence"),
])
def test_confidence_level_boundaries(confidence: float, level: str) -> None:
    result = calculate_map_strength({
        "all": aggregate(sample=confidence * 2, freshness=0, ct_rounds=0, t_rounds=0,
                         ct_rate=None, t_rate=None),
    }, TODAY)
    assert result.confidence_score == pytest.approx(confidence)
    assert result.confidence_level == level


@pytest.mark.parametrize("maps", [0, 1, 2])
def test_less_than_three_maps_has_no_strength(maps: int) -> None:
    result = calculate_map_strength({"all": aggregate(maps=maps)}, TODAY)
    assert result.status == "not_enough_data"
    assert result.map_strength_score is None
    assert result.confidence_level == "not_enough_data"


def test_three_maps_is_available_and_small_sample() -> None:
    result = calculate_map_strength({"all": aggregate(maps=3)}, TODAY)
    assert result.status == "available"
    assert result.map_strength_score is not None
    assert "small_sample" in result.warnings


def test_no_top30_warning() -> None:
    result = calculate_map_strength({"all": aggregate()}, TODAY)
    assert "no_matches_against_top_30" in result.warnings


def test_one_missing_side_is_used_and_warned() -> None:
    result = calculate_map_strength({"all": aggregate(ct_rate=62, t_rate=None)}, TODAY)
    assert factor(result, "side_strength").score == 62
    assert "missing_side_data" in result.warnings


@pytest.mark.parametrize(("age", "warning"), [(60, "stale_data"), (181, "very_stale_data")])
def test_freshness_warnings(age: int, warning: str) -> None:
    result = calculate_map_strength({"all": aggregate(age=age)}, TODAY)
    assert warning in result.warnings


def test_scores_are_clamped_to_valid_range() -> None:
    high = calculate_map_strength({"all": aggregate(map_rate=150, round_rate=150, ct_rate=150, t_rate=150,
                                                    sample=200, freshness=200)}, TODAY)
    low = calculate_map_strength({"all": aggregate(map_rate=-50, round_rate=-50, ct_rate=-50, t_rate=-50,
                                                   sample=-100, freshness=-100)}, TODAY)
    assert high.performance_score == pytest.approx(100)
    assert high.confidence_score == 100
    assert high.map_strength_score == pytest.approx(100)
    assert low.performance_score == 0 and low.confidence_score == 0 and low.map_strength_score == 25
