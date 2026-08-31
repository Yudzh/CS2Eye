import logging
from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from cs2eye.bot.api_client import CS2EyeAPIClient, CS2EyeAPIError, CS2EyeNotFoundError
from cs2eye.bot.formatters import (
    current_tournaments,
    format_form,
    format_h2h,
    format_he_kill_by_map,
    format_llm_analysis,
    format_llm_history,
    format_match_card,
    format_maps_veto,
    format_rosters,
    future_matches,
)
from cs2eye.bot.keyboards import (
    AnalysisCallback,
    MatchCallback,
    MatchDetailCallback,
    NavigationCallback,
    TournamentCallback,
    analysis_keyboard,
    analysis_run_keyboard,
    history_keyboard,
    main_menu_keyboard,
    match_keyboard,
    match_detail_keyboard,
    matches_keyboard,
    tournaments_keyboard,
)
from cs2eye.bot.navigation import NavigationState, navigation_state as default_navigation_state


logger = logging.getLogger(__name__)
router = Router(name=__name__)
ERROR_TEXT = "Не удалось получить данные CS2Eye. Попробуйте ещё раз."


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("<b>CS2Eye</b>", reply_markup=main_menu_keyboard())


@router.callback_query(NavigationCallback.filter(F.destination == "home"))
async def home(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit(callback, "<b>CS2Eye</b>", main_menu_keyboard())


@router.callback_query(NavigationCallback.filter(F.destination == "tournaments"))
async def tournaments(
    callback: CallbackQuery, api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    try:
        session = navigation_state.for_callback(callback)
        if session.tournaments is None:
            session.tournaments = await api_client.get_tournaments()
        items = current_tournaments(session.tournaments)
        text = "Выберите турнир:" if items else "Будущих турниров пока нет."
        await _edit(callback, text, tournaments_keyboard(items))
    except CS2EyeAPIError:
        logger.exception("Failed to load tournaments")
        await _edit(callback, ERROR_TEXT, main_menu_keyboard())


@router.callback_query(TournamentCallback.filter())
async def tournament_matches(
    callback: CallbackQuery,
    callback_data: TournamentCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    await _show_matches(
        callback, callback_data.tournament_id, api_client, navigation_state,
    )


@router.callback_query(NavigationCallback.filter(F.destination == "matches"))
async def back_to_matches(
    callback: CallbackQuery,
    callback_data: NavigationCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    await _show_matches(
        callback, callback_data.tournament_id, api_client, navigation_state,
    )


async def _show_matches(
    callback: CallbackQuery, tournament_id: int, api_client: CS2EyeAPIClient,
    navigation_state: NavigationState,
) -> None:
    try:
        session = navigation_state.for_callback(callback)
        cached = session.tournament_matches.get(tournament_id)
        if cached is None:
            selected = next(
                (
                    item for item in session.tournaments or []
                    if int(item.get("id", 0)) == tournament_id
                ),
                None,
            )
            if selected is None:
                selected = await api_client.get_tournament(tournament_id)
            matches = await api_client.get_tournament_matches(tournament_id)
            session.tournament_matches[tournament_id] = (selected, matches)
        else:
            selected, matches = cached
        items = future_matches(matches)
        title = escape(str(selected.get("name") or "Турнир"))
        text = f"<b>{title}</b>" if items else f"<b>{title}</b>\n\nБудущих матчей пока нет."
        await _edit(callback, text, matches_keyboard(items, tournament_id))
    except CS2EyeAPIError:
        logger.exception("Failed to load tournament %s matches", tournament_id)
        await _edit(callback, ERROR_TEXT, tournaments_keyboard([]))


@router.callback_query(MatchCallback.filter())
async def match_card(
    callback: CallbackQuery,
    callback_data: MatchCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    try:
        session = navigation_state.for_callback(callback)
        cached = session.match_cards.get(callback_data.match_id)
        if cached is not None:
            match, context = cached
            await _edit(
                callback, format_match_card(match, context),
                match_keyboard(callback_data.match_id, callback_data.tournament_id),
            )
            return
        match = await api_client.get_match(callback_data.match_id)
        team_a, team_b = match.get("team_a") or {}, match.get("team_b") or {}
        if team_a.get("id") is None or team_b.get("id") is None:
            raise CS2EyeAPIError(f"Match {callback_data.match_id} has incomplete teams")
        tournament = match.get("tournament") or {}
        context = await api_client.get_match_analysis_context(
            team_a_id=int(team_a["id"]),
            team_b_id=int(team_b["id"]),
            as_of=datetime.now(UTC),
            match_id=callback_data.match_id,
            tournament_id=tournament.get("id") or callback_data.tournament_id,
        )
        session.match_cards[callback_data.match_id] = (match, context)
        await _edit(
            callback,
            format_match_card(match, context),
            match_keyboard(callback_data.match_id, callback_data.tournament_id),
        )
    except (CS2EyeAPIError, KeyError, TypeError, ValueError):
        logger.exception("Failed to load match %s card", callback_data.match_id)
        await _edit(
            callback, ERROR_TEXT,
            match_keyboard(callback_data.match_id, callback_data.tournament_id),
        )


@router.callback_query(MatchDetailCallback.filter())
async def match_detail(
    callback: CallbackQuery,
    callback_data: MatchDetailCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    try:
        session = navigation_state.for_callback(callback)
        cached = session.match_cards.get(callback_data.match_id)
        if cached is None:
            match = await api_client.get_match(callback_data.match_id)
            team_a, team_b = match.get("team_a") or {}, match.get("team_b") or {}
            context = await api_client.get_match_analysis_context(
                team_a_id=int(team_a["id"]), team_b_id=int(team_b["id"]),
                as_of=datetime.now(UTC), match_id=callback_data.match_id,
                tournament_id=(match.get("tournament") or {}).get("id")
                or callback_data.tournament_id,
            )
            session.match_cards[callback_data.match_id] = (match, context)
        else:
            match, context = cached
        formatter = {
            "he_kill": lambda: format_he_kill_by_map(context),
            "maps": lambda: format_maps_veto(match, context),
            "form": lambda: format_form(context),
            "h2h": lambda: format_h2h(context),
            "rosters": lambda: format_rosters(context),
        }.get(callback_data.section)
        if formatter is None:
            raise ValueError(f"Unknown match detail section: {callback_data.section}")
        await _edit(
            callback, formatter(),
            match_detail_keyboard(callback_data.match_id, callback_data.tournament_id),
        )
    except (CS2EyeAPIError, KeyError, TypeError, ValueError):
        logger.exception(
            "Failed to load match %s detail %s",
            callback_data.match_id, callback_data.section,
        )
        await _edit(
            callback, ERROR_TEXT,
            match_detail_keyboard(callback_data.match_id, callback_data.tournament_id),
        )


@router.callback_query(AnalysisCallback.filter(F.action == "latest"))
async def latest_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    try:
        session = navigation_state.for_callback(callback)
        if callback_data.match_id in session.analyses:
            payload = session.analyses[callback_data.match_id]
            if payload is None:
                raise CS2EyeNotFoundError("missing in navigation session")
        else:
            match, team_a_id, team_b_id, _ = await _analysis_match(
                api_client, callback_data.match_id,
            )
            del match
            payload = await api_client.get_latest_llm_analysis(
                team_a_id=team_a_id, team_b_id=team_b_id,
                match_id=callback_data.match_id,
            )
            session.analyses[callback_data.match_id] = payload
        await _edit(
            callback, format_llm_analysis(payload),
            analysis_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                analysis_exists=True,
            ),
        )
    except CS2EyeNotFoundError:
        navigation_state.for_callback(callback).analyses[callback_data.match_id] = None
        await _edit(
            callback, "AI-анализ для этого матча ещё не создан.",
            analysis_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                analysis_exists=False,
            ),
        )
    except (CS2EyeAPIError, KeyError, TypeError, ValueError):
        logger.exception("Failed to load latest LLM analysis for match %s", callback_data.match_id)
        await _edit(
            callback, ERROR_TEXT,
            match_keyboard(callback_data.match_id, callback_data.tournament_id),
        )


@router.callback_query(AnalysisCallback.filter(F.action == "generate"))
async def generate_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    await _replace(
        callback, "Генерирую анализ...",
        match_keyboard(callback_data.match_id, callback_data.tournament_id),
    )
    try:
        _, team_a_id, team_b_id, tournament_id = await _analysis_match(
            api_client, callback_data.match_id,
        )
        payload = await api_client.generate_llm_analysis(
            team_a_id=team_a_id, team_b_id=team_b_id,
            as_of=datetime.now(UTC), match_id=callback_data.match_id,
            tournament_id=tournament_id or callback_data.tournament_id,
        )
        navigation_state.for_callback(callback).analyses[callback_data.match_id] = payload
        await _replace(
            callback, format_llm_analysis(payload),
            analysis_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                analysis_exists=True,
            ),
        )
    except (CS2EyeAPIError, KeyError, TypeError, ValueError):
        logger.exception("Failed to generate LLM analysis for match %s", callback_data.match_id)
        await _replace(
            callback, "Не удалось сгенерировать анализ. Попробуйте ещё раз.",
            analysis_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                analysis_exists=False,
            ),
        )


@router.callback_query(AnalysisCallback.filter(F.action == "history"))
async def analysis_history(
    callback: CallbackQuery,
    callback_data: AnalysisCallback,
    api_client: CS2EyeAPIClient,
) -> None:
    await callback.answer()
    try:
        history = await api_client.get_llm_analysis_history(match_id=callback_data.match_id)
        await _edit(
            callback, format_llm_history(history),
            history_keyboard(
                history, callback_data.match_id, callback_data.tournament_id,
            ),
        )
    except (CS2EyeAPIError, KeyError, TypeError, ValueError):
        logger.exception("Failed to load LLM history for match %s", callback_data.match_id)
        await _edit(
            callback, ERROR_TEXT,
            analysis_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                analysis_exists=True,
            ),
        )


@router.callback_query(AnalysisCallback.filter(F.action == "run"))
async def analysis_run(
    callback: CallbackQuery,
    callback_data: AnalysisCallback,
    api_client: CS2EyeAPIClient,
) -> None:
    await callback.answer()
    try:
        payload = await api_client.get_llm_analysis_run(callback_data.run_id)
        await _edit(
            callback, format_llm_analysis(payload),
            analysis_run_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                callback_data.run_id,
            ),
        )
    except CS2EyeNotFoundError:
        await _edit(
            callback, "Эта версия анализа больше не существует.",
            history_keyboard([], callback_data.match_id, callback_data.tournament_id),
        )
    except CS2EyeAPIError:
        logger.exception("Failed to load LLM run %s", callback_data.run_id)
        await _edit(
            callback, ERROR_TEXT,
            history_keyboard([], callback_data.match_id, callback_data.tournament_id),
        )


@router.callback_query(AnalysisCallback.filter(F.action == "regenerate"))
async def regenerate_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisCallback,
    api_client: CS2EyeAPIClient,
    navigation_state: NavigationState = default_navigation_state,
) -> None:
    await callback.answer()
    await _replace(
        callback, "Генерирую анализ...",
        analysis_run_keyboard(
            callback_data.match_id, callback_data.tournament_id, callback_data.run_id,
        ),
    )
    try:
        payload = await api_client.regenerate_llm_analysis(callback_data.run_id)
        navigation_state.for_callback(callback).analyses[callback_data.match_id] = payload
        new_run_id = int(payload["analysis_run_id"])
        await _replace(
            callback, format_llm_analysis(payload),
            analysis_run_keyboard(
                callback_data.match_id, callback_data.tournament_id, new_run_id,
            ),
        )
    except (CS2EyeAPIError, KeyError, TypeError, ValueError):
        logger.exception("Failed to regenerate LLM run %s", callback_data.run_id)
        await _replace(
            callback, "Не удалось сгенерировать анализ. Попробуйте ещё раз.",
            analysis_run_keyboard(
                callback_data.match_id, callback_data.tournament_id,
                callback_data.run_id,
            ),
        )


async def _analysis_match(
    api_client: CS2EyeAPIClient, match_id: int,
) -> tuple[dict, int, int, int | None]:
    match = await api_client.get_match(match_id)
    team_a, team_b = match.get("team_a") or {}, match.get("team_b") or {}
    if team_a.get("id") is None or team_b.get("id") is None:
        raise CS2EyeAPIError(f"Match {match_id} has incomplete teams")
    return (
        match, int(team_a["id"]), int(team_b["id"]),
        (match.get("tournament") or {}).get("id"),
    )


async def _edit(callback: CallbackQuery, text: str, reply_markup: object) -> None:
    await _replace(callback, text, reply_markup)


async def _replace(callback: CallbackQuery, text: str, reply_markup: object) -> None:
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    analysis_keyboard,
    analysis_run_keyboard,
    history_keyboard,
