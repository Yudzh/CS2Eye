from dataclasses import dataclass, field
from typing import Any
from time import monotonic

from aiogram.types import CallbackQuery


@dataclass
class UserNavigation:
    view_revision: int = 0
    bot_messages: set[tuple[int, int]] = field(default_factory=set)
    past_tournaments: bool = False
    tournaments: list[dict[str, Any]] | None = None
    tournament_matches: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = field(
        default_factory=dict,
    )
    match_cards: dict[int, tuple[dict[str, Any], dict[str, Any]]] = field(
        default_factory=dict,
    )
    match_card_times: dict[int, float] = field(default_factory=dict)
    match_summaries: dict[int, tuple[float, dict, dict]] = field(default_factory=dict)

    analyses: dict[int, dict[str, Any] | None] = field(default_factory=dict)

    def fresh_card(self, match_id: int, ttl: float = 30.0) -> tuple[dict[str, Any], dict[str, Any]] | None:
        saved = self.match_card_times.get(match_id)
        return self.match_cards.get(match_id) if saved is not None and monotonic()-saved < ttl else None

    def store_card(self, match_id: int, match: dict, context: dict) -> None:
        self.match_cards[match_id] = (match, context)
        self.match_card_times[match_id] = monotonic()

    def fresh_summary(self, match_id: int, ttl: float = 30.0):
        cached = self.match_summaries.get(match_id)
        return (cached[1], cached[2]) if cached and monotonic() - cached[0] < ttl else None

    def store_summary(self, match_id: int, match: dict, context: dict) -> None:
        self.match_summaries[match_id] = (monotonic(), match, context)



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
        session = self._users.setdefault(int(user_id), UserNavigation())
        self.track_message(session, getattr(callback, "message", None))
        return session

    def for_user(self, user_id: int) -> UserNavigation:
        return self._users.setdefault(int(user_id), UserNavigation())

    def for_message(self, message) -> UserNavigation:
        return self.for_user(message.from_user.id)

    @staticmethod
    def track_message(session, message):
        chat = getattr(message, "chat", None)
        message_id = getattr(message, "message_id", None)
        if chat is not None and chat.type == "private" and isinstance(message_id, int):
            session.bot_messages.add((chat.id, message_id))

    def reset_user(self, user_id: int) -> UserNavigation:
        previous = self._users.pop(int(user_id), UserNavigation())
        self._users[int(user_id)] = UserNavigation()
        return previous


navigation_state = NavigationState()
