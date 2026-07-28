from datetime import UTC, datetime, timedelta

from cs2eye.models.team import Player, TeamParticipantMembership
from cs2eye.services.team_strength_service import calculate_team_strength


NOW = datetime(2026, 7, 25, tzinfo=UTC)


def member(
    nickname: str,
    role: str | None,
    strength: int | None,
    *,
    days: int = 100,
    participant_type: str = "player",
    is_active: bool = True,
    left: bool = False,
) -> tuple[Player, TeamParticipantMembership]:
    player = Player(
        id=len(nickname) * 100 + sum(map(ord, nickname)),
        bo3_id=len(nickname) * 1000 + sum(map(ord, nickname)),
        bo3_slug=nickname,
        nickname=nickname,
        player_strength=strength,
    )
    membership = TeamParticipantMembership(
        team_id=1,
        player_id=player.id,
        participant_type=participant_type,
        role=role,
        is_active=is_active,
        joined_at=NOW - timedelta(days=days),
        left_at=NOW if left else None,
    )
    return player, membership


def test_exact_old_team_strength_logic() -> None:
    roster = [
        member("weak_awper", "awper", 35),
        member("captain", "igl", 60),
        member("rifler1", "rifler", 60),
        member("rifler2", "lurk", 60),
        member("rifler3", "anchor_support", 60),
        member("coach", None, 100, participant_type="coach"),
        member("former", "rifler", 100, left=True),
    ]

    result = calculate_team_strength(roster, now=NOW)

    assert result.active_players_count == 5
    assert result.base_player_score == 55
    assert result.roster_bonus == 10
    assert result.roster_penalty == 15
    assert result.total_adjustment == -5
    assert result.score_before_limits == 50
    assert result.team_strength_score == 50
    assert result.calculation == "55.00 + 10.00 - 15.00 = 50.00"
    assert {factor.code for factor in result.factors} >= {
        "base_player_score", "awper_strength", "stable_roster_90_days",
    }


def test_missing_strength_defaults_to_fifty() -> None:
    roster = [
        member("awper", "awper", None, days=20),
        member("igl", "igl", None, days=20),
        member("one", "rifler", None, days=20),
        member("two", "lurk", None, days=20),
        member("three", "entry_frag", None, days=20),
    ]

    result = calculate_team_strength(roster, now=NOW)

    assert result.base_player_score == 50
    assert result.team_strength_score == 45
