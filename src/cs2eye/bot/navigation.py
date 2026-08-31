from dataclasses import dataclass, field
from typing import Any

from aiogram.types import CallbackQuery


@dataclass
class UserNavigation:
    tournaments: list[dict[str, Any]] | None = None
    tournament_matches: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = field(
        default_factory=dict,
    )
    match_cards: dict[int, tuple[dict[str, Any], dict[str, Any]]] = field(
        default_factory=dict,
    )
    analyses: dict[int, dict[str, Any] | None] = field(default_factory=dict)


class NavigationState:
    """Process-local navigation snapshots, isolated by Telegram user."""

    def __init__(self) -> None:
        self._users: dict[int, UserNavigation] = {}
        self._anonymous_callbacks: dict[int, tuple[object, UserNavigation]] = {}

    def for_callback(self, callback: CallbackQuery) -> UserNavigation:
        user = getattr(callback, "from_user", None)
        user_id = getattr(user, "id", None)
        if user_id is None:
            # Useful for lightweight handler tests; real callbacks always have from_user.
            callback_id = id(callback)
            existing = self._anonymous_callbacks.get(callback_id)
            if existing is not None and existing[0] is callback:
                return existing[1]
            session = UserNavigation()
            # Keep a strong reference so Python cannot recycle the identity while
            # this fallback state exists.
            self._anonymous_callbacks[callback_id] = (callback, session)
            return session
        return self._users.setdefault(int(user_id), UserNavigation())


navigation_state = NavigationState()
