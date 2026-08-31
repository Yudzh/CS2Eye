from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class TournamentCallback(CallbackData, prefix="tournament"):
    tournament_id: int


class MatchCallback(CallbackData, prefix="match"):
    match_id: int
    tournament_id: int


class NavigationCallback(CallbackData, prefix="nav"):
    destination: str
    tournament_id: int = 0


class AnalysisCallback(CallbackData, prefix="ai"):
    action: str
    match_id: int
    tournament_id: int
    run_id: int = 0


class MatchDetailCallback(CallbackData, prefix="detail"):
    section: str
    match_id: int
    tournament_id: int


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Будущие турниры",
            callback_data=NavigationCallback(destination="tournaments").pack(),
        ),
    ]])


def tournaments_keyboard(tournaments: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=str(item.get("name") or "Турнир"),
        callback_data=TournamentCallback(tournament_id=int(item["id"])).pack(),
    )] for item in tournaments]
    rows.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavigationCallback(destination="home").pack(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def matches_keyboard(
    matches: list[dict[str, Any]], tournament_id: int,
) -> InlineKeyboardMarkup:
    rows = []
    for item in matches:
        team_a = (item.get("team_a") or {}).get("name") or "?"
        team_b = (item.get("team_b") or {}).get("name") or "?"
        rows.append([InlineKeyboardButton(
            text=f"{team_a} vs {team_b}",
            callback_data=MatchCallback(
                match_id=int(item["id"]), tournament_id=tournament_id,
            ).pack(),
        )])
    rows.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=NavigationCallback(destination="tournaments").pack(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def match_keyboard(match_id: int, tournament_id: int) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(
            text="AI-анализ",
            callback_data=AnalysisCallback(
                action="latest", match_id=match_id, tournament_id=tournament_id,
            ).pack(),
        ),
    ]]
    for label, section in (
        ("HE Kill", "he_kill"),
        ("Карты / veto", "maps"), ("Форма", "form"),
        ("H2H", "h2h"), ("Составы", "rosters"),
    ):
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=MatchDetailCallback(
                section=section, match_id=match_id, tournament_id=tournament_id,
            ).pack(),
        )])
    rows.append([
        InlineKeyboardButton(
            text="← Назад к матчам",
            callback_data=NavigationCallback(
                destination="matches", tournament_id=tournament_id,
            ).pack(),
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def match_detail_keyboard(match_id: int, tournament_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="← Назад к матчу",
            callback_data=MatchCallback(
                match_id=match_id, tournament_id=tournament_id,
            ).pack(),
        ),
    ]])


def analysis_keyboard(
    match_id: int, tournament_id: int, *, analysis_exists: bool,
) -> InlineKeyboardMarkup:
    action = "generate"
    label = "Обновить анализ" if analysis_exists else "Сгенерировать анализ"
    rows = [[InlineKeyboardButton(
        text=label,
        callback_data=AnalysisCallback(
            action=action, match_id=match_id, tournament_id=tournament_id,
        ).pack(),
    )]]
    rows.append([InlineKeyboardButton(
        text="← Назад",
        callback_data=MatchCallback(match_id=match_id, tournament_id=tournament_id).pack(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_keyboard(
    history: list[dict[str, Any]], match_id: int, tournament_id: int,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"Версия {index}",
        callback_data=AnalysisCallback(
            action="run", match_id=match_id, tournament_id=tournament_id,
            run_id=int(item["id"]),
        ).pack(),
    )] for index, item in enumerate(history, 1)]
    rows.append([InlineKeyboardButton(
        text="← Назад к AI-анализу",
        callback_data=AnalysisCallback(
            action="latest", match_id=match_id, tournament_id=tournament_id,
        ).pack(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def analysis_run_keyboard(
    match_id: int, tournament_id: int, run_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Перегенерировать эту версию",
            callback_data=AnalysisCallback(
                action="regenerate", match_id=match_id,
                tournament_id=tournament_id, run_id=run_id,
            ).pack(),
        ),
    ], [
        InlineKeyboardButton(
            text="← Назад к истории",
            callback_data=AnalysisCallback(
                action="history", match_id=match_id, tournament_id=tournament_id,
            ).pack(),
        ),
    ]])
