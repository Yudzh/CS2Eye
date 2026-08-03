import pytest

from cs2eye.services.team_roster_service import build_roster_fingerprint


def test_fingerprint_is_order_independent() -> None:
    assert build_roster_fingerprint([1, 2, 3, 4, 5]) == build_roster_fingerprint([5, 3, 1, 4, 2])


def test_one_changed_player_changes_fingerprint() -> None:
    assert build_roster_fingerprint([1, 2, 3, 4, 5]) != build_roster_fingerprint([1, 2, 3, 4, 6])


@pytest.mark.parametrize("players", [[], [1, 2, 3, 4], [1, 2, 3, 4, 4], [1, 2, 3, 4, 5, 6]])
def test_complete_fingerprint_requires_five_unique_players(players: list[int]) -> None:
    with pytest.raises(ValueError):
        build_roster_fingerprint(players)
