from uuid import uuid4

from cs2eye.services.team_dashboard_service import (
    build_roster_state,
    calculate_relative_strength_percentages,
)
from cs2eye.services.team_service import TeamStrengthInfo


def _strength(
        *,
        active_players_count: int = 5,
        notes: list[str] | None = None,
) -> TeamStrengthInfo:
    return TeamStrengthInfo(
        team_id=uuid4(),
        team_name="Test Team",

        active_players_count=active_players_count,
        base_player_score=70.0,

        roster_bonus=0.0,
        roster_penalty=0.0,
        total_adjustment=0.0,

        score_before_limits=70.0,
        team_strength_score=70.0,

        calculation=(
            "70.00 + 0.00 "
            "- 0.00 = 70.00"
        ),

        missing_required_roles=[],
        factors=[],
        notes=notes or [],
    )


def test_relative_strength_percentages_sum_to_100() -> None:
    team_a_percent, team_b_percent = (
        calculate_relative_strength_percentages(
            70.0,
            60.0,
        )
    )

    assert team_a_percent == 53.85
    assert team_b_percent == 46.15
    assert team_a_percent + team_b_percent == 100.0


def test_relative_strength_percentages_are_empty_without_scores() -> None:
    assert calculate_relative_strength_percentages(
        0.0,
        0.0,
    ) == (None, None)


def test_incomplete_roster_has_highest_priority() -> None:
    state = build_roster_state(
        _strength(
            active_players_count=4,
            notes=["Состав стабилен минимум 90 дней."],
        )
    )

    assert state.code == "incomplete"


def test_stable_roster_is_detected() -> None:
    state = build_roster_state(
        _strength(
            notes=["Состав стабилен минимум 90 дней."]
        )
    )

    assert state.code == "stable"