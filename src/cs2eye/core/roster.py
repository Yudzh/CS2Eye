from collections.abc import Iterable
from datetime import date
from typing import Protocol, TypeVar


ACTIVE_ROSTER_SIZE = 5

ROSTER_STATUS_ACTIVE = "active"
ROSTER_STATUS_COACH = "coach"

VALID_ROSTER_STATUSES = frozenset({
    ROSTER_STATUS_ACTIVE,
    ROSTER_STATUS_COACH,
})


class RosterEntry(Protocol):
    status: str
    left_at: date | None


RosterEntryT = TypeVar(
    "RosterEntryT",
    bound=RosterEntry,
)


def is_current_active_player(
        item: RosterEntry,
) -> bool:
    return (
        item.status == ROSTER_STATUS_ACTIVE
        and item.left_at is None
    )


def is_current_coach(
        item: RosterEntry,
) -> bool:
    return (
        item.status == ROSTER_STATUS_COACH
        and item.left_at is None
    )


def get_current_active_players(
        items: Iterable[RosterEntryT],
) -> list[RosterEntryT]:
    return [
        item
        for item in items
        if is_current_active_player(item)
    ]


def get_current_coaches(
        items: Iterable[RosterEntryT],
) -> list[RosterEntryT]:
    return [
        item
        for item in items
        if is_current_coach(item)
    ]