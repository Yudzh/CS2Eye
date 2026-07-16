import pytest

from cs2eye.services.liquipedia_team_import_service import (
    LiquipediaRosterPlayer,
    LiquipediaTeamRosterDraft,
    apply_liquipedia_role_assignments,
)


def _player(
        nickname: str,
        *,
        status: str = "active",
        role: str | None = None,
) -> LiquipediaRosterPlayer:
    return LiquipediaRosterPlayer(
        nickname=nickname,
        real_name=None,
        country=None,
        status=status,
        role=role,
        joined_at=None,
        left_at=None,
        liquipedia_url=None,
        source_url="https://liquipedia.test",
        source_confidence=0.7,
        notes=None,
    )


def _draft() -> LiquipediaTeamRosterDraft:
    return LiquipediaTeamRosterDraft(
        team_name="Test Team",
        liquipedia_url=(
            "https://liquipedia.test/Test_Team"
        ),
        players=[
            _player("player1"),
            _player("player2"),
            _player("player3"),
            _player("player4"),
            _player("player5"),
            _player(
                "coach1",
                status="coach",
            ),
        ],
        warnings=[],
    )


def test_roles_are_applied_to_players() -> None:
    result = apply_liquipedia_role_assignments(
        draft=_draft(),
        role_assignments=[
            {
                "nickname": "player1",
                "role": "igl",
            },
            {
                "nickname": "player2",
                "role": "awper",
            },
            {
                "nickname": "player3",
                "role": "entry_frag",
            },
            {
                "nickname": "player4",
                "role": "lurk",
            },
            {
                "nickname": "player5",
                "role": "anchor_support",
            },
        ],
    )

    roles = {
        player.nickname: player.role
        for player in result.players
    }

    assert roles == {
        "player1": "igl",
        "player2": "awper",
        "player3": "entry_frag",
        "player4": "lurk",
        "player5": "anchor_support",
        "coach1": "coach",
    }


def test_save_is_blocked_without_roles() -> None:
    with pytest.raises(
        ValueError,
        match="Select a role",
    ):
        apply_liquipedia_role_assignments(
            draft=_draft(),
            role_assignments=[],
        )


def test_active_player_cannot_be_coach() -> None:
    assignments = [
        {
            "nickname": f"player{index}",
            "role": role,
        }
        for index, role in enumerate(
            [
                "coach",
                "awper",
                "entry_frag",
                "lurk",
                "anchor_support",
            ],
            start=1,
        )
    ]

    with pytest.raises(
        ValueError,
        match="cannot have coach role",
    ):
        apply_liquipedia_role_assignments(
            draft=_draft(),
            role_assignments=assignments,
        )