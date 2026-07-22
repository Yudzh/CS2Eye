from dataclasses import dataclass
from datetime import date

from cs2eye.core.roster import (
    get_current_active_players,
    get_current_coaches,
)


@dataclass(frozen=True)
class TestRosterEntry:
    status: str
    left_at: date | None


def test_current_active_players_rule(
) -> None:
    current_active = TestRosterEntry(
        status="active",
        left_at=None,
    )

    former_active = TestRosterEntry(
        status="active",
        left_at=date(2026, 1, 1),
    )

    coach = TestRosterEntry(
        status="coach",
        left_at=None,
    )

    stand_in = TestRosterEntry(
        status="stand-in",
        left_at=None,
    )

    items = [
        current_active,
        former_active,
        coach,
        stand_in,
    ]

    assert get_current_active_players(
        items
    ) == [
        current_active,
    ]

    assert get_current_coaches(
        items
    ) == [
        coach,
    ]