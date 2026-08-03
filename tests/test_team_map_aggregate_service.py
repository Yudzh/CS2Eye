from datetime import date, timedelta

import pytest

from cs2eye.services.team_map_aggregate_service import (
    calculate_freshness_score, calculate_sample_size_score, freshness_label,
    sample_size_label,
)


@pytest.mark.parametrize(("maps", "score"), [
    (0, 0), (1, 15), (2, 25), (3, 35), (5, 50), (8, 65),
    (10, 75), (15, 90), (20, 100), (40, 100),
])
def test_sample_size_score_control_points(maps: int, score: float) -> None:
    assert calculate_sample_size_score(maps) == score


def test_sample_size_score_interpolates() -> None:
    assert calculate_sample_size_score(4) == 42.5


@pytest.mark.parametrize(("maps", "label"), [
    (0, "no_data"), (1, "very_low"), (2, "very_low"), (3, "low"),
    (5, "medium"), (10, "good"), (15, "high"),
])
def test_sample_size_label(maps: int, label: str) -> None:
    assert sample_size_label(maps) == label


@pytest.mark.parametrize(("days", "score", "label"), [
    (0, 100, "fresh"), (7, 100, "fresh"), (14, 90, "fresh"),
    (30, 75, "acceptable"), (60, 55, "stale"), (90, 35, "stale"),
    (180, 15, "very_stale"), (181, 5, "very_stale"),
])
def test_freshness(days: int, score: float, label: str) -> None:
    today = date(2026, 7, 30)
    last = today - timedelta(days=days)
    assert calculate_freshness_score(last, today) == score
    assert freshness_label(last, today) == label


def test_missing_date_has_unknown_freshness() -> None:
    assert calculate_freshness_score(None, date(2026, 7, 30)) == 0
    assert freshness_label(None, date(2026, 7, 30)) == "unknown"
