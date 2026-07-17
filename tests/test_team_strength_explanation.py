from datetime import (
    date,
    timedelta,
)
from uuid import uuid4

from cs2eye.models.team import Team
from cs2eye.services.team_service import (
    RosterMemberInfo,
    calculate_team_strength,
)


def _member(
        nickname: str,
        role: str,
        strength: float,
) -> RosterMemberInfo:
    return RosterMemberInfo(
        roster_member_id=uuid4(),

        player_id=uuid4(),
        nickname=nickname,

        real_name=None,
        country=None,

        status="active",
        role=role,

        joined_at=(
            date.today()
            - timedelta(days=100)
        ),

        left_at=None,

        current_rating=None,

        player_strength_score=(
            strength
        ),

        source_name="test",
        source_url=None,
        source_confidence=1.0,

        notes=None,
    )


def test_strength_has_explanation_factors(
) -> None:
    team = Team(
        id=uuid4(),
        name="Test Team",
    )

    roster = [
        _member(
            "weak_awper",
            "awper",
            35.0,
        ),
        _member(
            "captain",
            "igl",
            60.0,
        ),
        _member(
            "rifler1",
            "rifler",
            60.0,
        ),
        _member(
            "rifler2",
            "lurk",
            60.0,
        ),
        _member(
            "rifler3",
            "anchor_support",
            60.0,
        ),
    ]

    result = calculate_team_strength(
        team=team,
        roster=roster,
    )

    assert result.base_player_score == 55.0

    assert result.roster_bonus == 10.0
    assert result.roster_penalty == 15.0

    assert result.total_adjustment == -5.0

    assert result.score_before_limits == 50.0
    assert result.team_strength_score == 50.0

    factor_values = {
        factor.code: factor.value
        for factor in result.factors
    }

    assert factor_values[
        "stable_roster_90_days"
    ] == 10.0

    assert factor_values[
        "awper_strength"
    ] == -15.0

    assert result.calculation == (
        "55.00 + 10.00 "
        "- 15.00 = 50.00"
    )