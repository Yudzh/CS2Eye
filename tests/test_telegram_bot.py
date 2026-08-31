from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from cs2eye.bot.api_client import CS2EyeAPIClient, CS2EyeAPIError, CS2EyeNotFoundError
from cs2eye.bot.formatters import (
    current_tournaments, format_form, format_h2h, format_he_kill_by_map, format_llm_analysis,
    format_llm_history, format_maps_veto, format_match_card, format_rosters,
    future_matches,
)
from cs2eye.bot.handlers import (
    ERROR_TEXT, analysis_history, analysis_run, back_to_matches,
    generate_analysis, latest_analysis, match_card, match_detail, regenerate_analysis,
    tournament_matches, tournaments,
)
from cs2eye.bot.keyboards import (
    AnalysisCallback, MatchCallback, MatchDetailCallback, NavigationCallback,
    TournamentCallback,
)
from cs2eye.bot.navigation import NavigationState


def match_payload() -> dict:
    return {
        "id": 42,
        "match_date": "2099-05-02",
        "format": "bo3",
        "stage": "quarterfinal",
        "environment": "lan",
        "status": "scheduled",
        "team_a": {"id": 1, "name": "FURIA"},
        "team_b": {"id": 2, "name": "Legacy"},
        "tournament": {"id": 7, "name": "IEM Chengdu"},
    }


def context_payload(*, prediction_available: bool = True, navi: bool = False, group: bool = False) -> dict:
    payload = {
        "match": {
            "format": "bo3", "environment": "lan", "stage": "quarterfinal",
            "round_label": None,
            "tournament": {"id": 7, "name": "IEM Chengdu"},
        },
        "teams": {
            "team_a": {"id": 1, "name": "FURIA"},
            "team_b": {"id": 2, "name": "Legacy"},
        },
        "prediction": {
            "status": "available" if prediction_available else "not_available",
            "team_a_probability": .54 if prediction_available else None,
            "team_b_probability": .46 if prediction_available else None,
        },
        "matchup": {
            "team_a_score": 51.2,
            "team_b_score": 48.8,
            "reliability": .82,
            "confidence_level": "medium",
        },
        "data_quality": {"overall_status": "partial"},
        "secondary_bets": {"he_kill_by_map": [
            {"map": name, "probability": probability, "confidence": confidence,
             "team_a_sample": index, "team_b_sample": index + 1}
            for index, (name, probability, confidence) in enumerate((
                ("inferno", .69, "medium"), ("ancient", .64, "high"),
                ("train", .57, "low"), ("mirage", .51, "medium"),
                ("nuke", .47, "medium"), ("overpass", .43, "low"),
                ("dust2", .38, "medium"),
            ), 1)
        ]},
    }
    payload["betting_restrictions"] = {
        "restricted": navi,
        "rule": "navi_no_match_winner_bets" if navi else None,
        "message": "НЕ СТАВИТЬ НА NAVI И НЕ СТАВИТЬ ПРОТИВ NAVI.\n\nДля матчей NAVI рассматривать только сторонние рынки, не зависящие напрямую от победителя матча, например тоталы." if navi else None,
    }
    items = []
    if navi:
        items.append({"rule": payload["betting_restrictions"]["rule"], "message": payload["betting_restrictions"]["message"]})
    if group:
        items.append({"rule": "group_stage_no_match_winner_bets", "message": "НЕ СТАВИТЬ НА ПОБЕДИТЕЛЯ МАТЧА."})
    if items:
        payload["betting_restrictions"].update({"restricted": True, "rule": items[0]["rule"], "message": items[0]["message"], "restrictions": items})
    return payload


def analysis_payload(*, run_id: int = 101) -> dict:
    return {
        "analysis_run_id": run_id,
        "status": "completed",
        "created_at": "2026-08-29T14:30:00Z",
        "runtime": {
            "provider": "ollama", "model": "qwen3:8b",
            "prompt_version": "match_analysis_prompt.v3",
        },
        "rendered_analysis": {
            "summary": "FURIA имеет небольшое преимущество.",
            "advantages": [{"text": "Более сильная текущая форма."}],
            "counter_arguments": [{"text": "Legacy может навязать борьбу."}],
            "contradictions": [],
            "risks": [{"text": "Небольшая выборка."}],
            "limitations": [],
        },
        "analysis": None,
    }


def detail_context_payload() -> dict:
    return {
        "teams": {
            "team_a": {"name": "Aurora", "form": {
                "tournament_form_score": 50.6, "tournament_matches": 2,
                "recent_60d_score": 51.4, "recent_60d_matches": 6,
                "strength_of_schedule_score": 61.2,
                "performance_vs_expectation_score": 32.6,
            }, "roster": {
                "players": [
                    {"name": "XANTARES", "role": "IGL"},
                    {"name": "woxic", "role": None},
                ], "coach": {"name": "ashhh"}, "stability_score": 54.6,
            }},
            "team_b": {"name": "M80", "form": {
                "tournament_form_score": 60.0, "tournament_matches": 2,
                "recent_60d_score": 49.1, "recent_60d_matches": 5,
                "strength_of_schedule_score": 80.7,
                "performance_vs_expectation_score": 70.2,
            }, "roster": {
                "players": [{"name": "s1n", "role": "stand-in"}],
                "coach": {"name": "dephh"}, "stability_score": None,
            }},
        },
        "veto": {"basis": "calculated_veto", "likely_maps": [
            {"map": "anubis"}, {"map": "dust2"}, {"map": "inferno"},
        ]},
        "map_matchups": [
            {"map": "anubis", "team_a": {"map_strength": 59.1},
             "team_b": {"map_strength": None},
             "key_edges": [{"favored_team": "team_a", "metric": "t_side"}]},
            {"map": "dust2", "team_a": {"map_strength": 51.3},
             "team_b": {"map_strength": 31.8}, "key_edges": []},
            {"map": "inferno", "team_a": {"map_strength": None},
             "team_b": {"map_strength": 42.7},
             "key_edges": [{"favored_team": "team_b", "metric": "ct_side"}]},
        ],
        "h2h": {
            "organizations": {"status": "available", "series_played": 3,
                "maps_played": 7, "team_a_series_won": 2, "team_b_series_won": 1},
            "current_rosters": {"status": "available", "series_played": 1,
                "maps_played": 2, "team_a_series_won": 1, "team_b_series_won": 0},
        },
    }


def callback(*, user_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
        from_user=SimpleNamespace(id=user_id) if user_id is not None else None,
    )


def test_formats_match_card_using_backend_confidence_level() -> None:
    text = format_match_card(match_payload(), context_payload())
    assert "FURIA — 54%" in text
    assert "Legacy — 46%" in text
    assert "FURIA — 51.2" in text
    assert "Confidence: Medium" in text
    assert "Data quality: Partial" in text


def test_formats_unavailable_ml_without_substituting_matchup() -> None:
    text = format_match_card(match_payload(), context_payload(prediction_available=False))
    assert "ML prediction:</b> unavailable" in text
    assert "FURIA — 51.2" in text
    assert "FURIA — 54%" not in text


def test_navi_warning_is_at_top_of_telegram_match_card() -> None:
    text = format_match_card(match_payload(), context_payload(navi=True))
    assert text.startswith("⚠️ <b>NAVI RULE</b>")
    assert "НЕ СТАВИТЬ НА NAVI И НЕ СТАВИТЬ ПРОТИВ NAVI." in text
    assert "FURIA — 54%" in text


def test_navi_warning_is_at_top_of_telegram_ai_presentation() -> None:
    payload = {**analysis_payload(), "context": context_payload(navi=True)}
    text = format_llm_analysis(payload)
    assert text.startswith("⚠️ <b>NAVI RULE</b>")
    assert "Кратко:" in text


def test_group_warning_is_shown_in_telegram_match_and_ai_presentations() -> None:
    context = context_payload(group=True)
    card = format_match_card(match_payload(), context)
    analysis = format_llm_analysis({**analysis_payload(), "context": context})
    assert card.startswith("⚠️ <b>GROUP STAGE RULE</b>")
    assert analysis.startswith("⚠️ <b>GROUP STAGE RULE</b>")
    assert "НЕ СТАВИТЬ НА ПОБЕДИТЕЛЯ МАТЧА." in card


def test_navi_and_group_warnings_are_both_shown_in_telegram_order() -> None:
    text = format_match_card(match_payload(), context_payload(navi=True, group=True))
    assert text.index("NAVI RULE") < text.index("GROUP STAGE RULE") < text.index("FURIA vs Legacy")


def test_formats_he_kill_in_backend_order_with_confidence() -> None:
    text = format_he_kill_by_map(context_payload())
    expected = ["Inferno — 69% · Medium", "Ancient — 64% · High",
                "Train — 57% · Low", "Mirage — 51% · Medium",
                "Nuke — 47% · Medium", "Overpass — 43% · Low",
                "Dust2 — 38% · Medium"]
    assert all(value in text for value in expected)
    assert [text.index(value) for value in expected] == sorted(text.index(value) for value in expected)


def test_formats_unavailable_he_kill() -> None:
    assert "HE Kill prediction unavailable" in format_he_kill_by_map({})


def test_filters_and_orders_current_tournaments() -> None:
    items = current_tournaments([
        {"id": 1, "name": "Past", "start_date": "2026-01-01", "end_date": "2026-01-02"},
        {"id": 2, "name": "Later", "start_date": "2026-09-02", "end_date": "2026-09-05"},
        {"id": 3, "name": "Current", "start_date": "2026-08-20", "end_date": "2026-08-30"},
    ], today=date(2026, 8, 29))
    assert [item["id"] for item in items] == [3, 2]


def test_filters_matches_for_pre_match_flow() -> None:
    valid = match_payload()
    completed = {**valid, "id": 43, "status": "completed"}
    unknown_team = {**valid, "id": 44, "team_b": {"id": None, "name": None}}
    assert future_matches(
        [completed, unknown_team, valid], today=date(2099, 5, 1)
    ) == [valid]


async def test_tournaments_callback_edits_existing_message() -> None:
    event = callback()
    client = SimpleNamespace(get_tournaments=AsyncMock(return_value=[{
        "id": 7, "name": "IEM Chengdu",
        "start_date": "2099-05-01", "end_date": "2099-05-10",
    }]))
    await tournaments(event, client)
    text, = event.message.edit_text.await_args.args
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert text == "Выберите турнир:"
    assert keyboard.inline_keyboard[0][0].callback_data == "tournament:7"
    event.answer.assert_awaited_once()


async def test_matches_navigation_uses_tournament_callback_id() -> None:
    event = callback()
    client = SimpleNamespace(
        get_tournament=AsyncMock(return_value={"id": 7, "name": "IEM Chengdu"}),
        get_tournament_matches=AsyncMock(return_value=[match_payload()]),
    )
    data = NavigationCallback(destination="matches", tournament_id=7)
    await back_to_matches(event, data, client)
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "match:42:7"
    client.get_tournament_matches.assert_awaited_once_with(7)


async def test_match_callback_loads_context_from_backend() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_match_analysis_context=AsyncMock(return_value=context_payload()),
    )
    await match_card(event, MatchCallback(match_id=42, tournament_id=7), client)
    kwargs = client.get_match_analysis_context.await_args.kwargs
    assert kwargs["team_a_id"] == 1
    assert kwargs["team_b_id"] == 2
    assert kwargs["match_id"] == 42
    assert "Confidence: Medium" in event.message.edit_text.await_args.args[0]
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "ai:latest:42:7:0"
    assert any(button.text == "HE Kill" for row in keyboard.inline_keyboard for button in row)


async def test_he_kill_navigation_reuses_cached_match_context() -> None:
    state = NavigationState()
    first = callback(user_id=777)
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_match_analysis_context=AsyncMock(return_value=context_payload()),
    )
    await match_card(first, MatchCallback(match_id=42, tournament_id=7), client, state)
    detail = callback(user_id=777)
    await match_detail(
        detail, MatchDetailCallback(section="he_kill", match_id=42, tournament_id=7),
        client, state,
    )
    assert "Inferno — 69% · Medium" in detail.message.edit_text.await_args.args[0]
    keyboard = detail.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "← Назад к матчу"
    back = callback(user_id=777)
    await match_card(back, MatchCallback(match_id=42, tournament_id=7), client, state)
    client.get_match.assert_awaited_once()
    client.get_match_analysis_context.assert_awaited_once()


async def test_backend_error_is_shown_without_escaping_handler() -> None:
    event = callback()
    client = SimpleNamespace(
        get_tournaments=AsyncMock(side_effect=CS2EyeAPIError("backend down")),
    )
    await tournaments(event, client)
    assert event.message.edit_text.await_args.args[0] == ERROR_TEXT
    event.answer.assert_awaited_once()


async def test_api_client_wraps_backend_5xx() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    http_client = httpx.AsyncClient(
        base_url="http://backend", transport=httpx.MockTransport(respond),
    )
    client = CS2EyeAPIClient("http://backend", client=http_client)
    try:
        try:
            await client.get_tournaments()
        except CS2EyeAPIError as error:
            assert "503" in str(error)
        else:
            raise AssertionError("CS2EyeAPIError was not raised")
    finally:
        await http_client.aclose()


async def test_api_client_uses_long_timeout_for_llm_generation() -> None:
    captured: dict = {}

    async def respond(request: httpx.Request) -> httpx.Response:
        captured.update(request.extensions["timeout"])
        return httpx.Response(200, request=request, json=analysis_payload())

    http_client = httpx.AsyncClient(
        base_url="http://backend", timeout=15,
        transport=httpx.MockTransport(respond),
    )
    client = CS2EyeAPIClient(
        "http://backend", client=http_client, generation_timeout=330,
    )
    try:
        await client.generate_llm_analysis(
            team_a_id=1, team_b_id=2, as_of=date(2026, 8, 29),
            match_id=42, tournament_id=7,
        )
        assert captured["read"] == 330
    finally:
        await http_client.aclose()


def test_llm_formatter_hides_empty_sections() -> None:
    text = format_llm_analysis(analysis_payload())
    assert "Кратко:" in text
    assert "Преимущества:" in text
    assert "Контраргументы:" in text
    assert "Риски:" in text
    assert "Противоречия:" not in text
    assert "Ограничения:" not in text


def test_llm_v3_formatter_always_renders_five_fixed_sections() -> None:
    payload = {"status": "completed", "analysis": {
        "schema_version": "match_llm_analysis.v3",
        "explanation_plan_version": "match_explanation_plan.v2",
        "conclusion_text": "Итог", "form_text": "Форма",
        "maps_text": "Карты", "teamplay_text": "Тимплей",
        "manual_text": "Ручных комментариев нет.",
    }}
    text = format_llm_analysis(payload)
    positions = [text.index(title) for title in (
        "📌 <b>Итог</b>", "📈 <b>Форма</b>", "🗺 <b>Карты</b>",
        "🎯 <b>Тимплей и свинги</b>", "📝 <b>Ручная аналитика</b>",
    )]
    assert positions == sorted(positions)


async def test_latest_analysis_exists() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_latest_llm_analysis=AsyncMock(return_value={
            **analysis_payload(),
            "analysis": {
                "schema_version": "match_llm_analysis.v3",
                "conclusion_text": "Итог", "form_text": "Форма",
                "maps_text": "Карты", "teamplay_text": "Тимплей",
                "manual_text": "Ручных комментариев нет.",
            },
            "explanation_plan": {"expected_winner": {
                "team_id": 1, "team_name": "FURIA", "win_probability": .57,
            }},
        }),
    )
    data = AnalysisCallback(action="latest", match_id=42, tournament_id=7)
    await latest_analysis(event, data, client)
    assert "По расчётам должна выиграть FURIA — 57%" in event.message.edit_text.await_args.args[0]
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "Обновить анализ"
    assert [button.text for row in keyboard.inline_keyboard for button in row] == [
        "Обновить анализ", "← Назад",
    ]


async def test_latest_analysis_absent() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_latest_llm_analysis=AsyncMock(side_effect=CS2EyeNotFoundError("missing")),
    )
    await latest_analysis(
        event, AnalysisCallback(action="latest", match_id=42, tournament_id=7), client,
    )
    assert event.message.edit_text.await_args.args[0] == "AI-анализ для этого матча ещё не создан."
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "Сгенерировать анализ"


async def test_generate_analysis_uses_backend_and_displays_new_run() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        generate_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=102)),
    )
    await generate_analysis(
        event, AnalysisCallback(action="generate", match_id=42, tournament_id=7), client,
    )
    assert event.message.edit_text.await_count == 2
    assert event.message.edit_text.await_args_list[0].args[0] == "Генерирую анализ..."
    assert "Кратко:" in event.message.edit_text.await_args_list[1].args[0]
    assert client.generate_llm_analysis.await_args.kwargs["match_id"] == 42


async def test_generate_analysis_error_is_safe() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        generate_llm_analysis=AsyncMock(side_effect=CS2EyeAPIError("provider failed")),
    )
    await generate_analysis(
        event, AnalysisCallback(action="generate", match_id=42, tournament_id=7), client,
    )
    assert event.message.edit_text.await_args.args[0] == "Не удалось сгенерировать анализ. Попробуйте ещё раз."


async def test_history_and_navigation_buttons() -> None:
    event = callback()
    history = [{
        "id": 101, "created_at": "2026-08-29T14:30:00Z", "status": "completed",
        "model": "qwen3:8b", "prompt_version": "match_analysis_prompt.v3",
    }]
    client = SimpleNamespace(get_llm_analysis_history=AsyncMock(return_value=history))
    await analysis_history(
        event, AnalysisCallback(action="history", match_id=42, tournament_id=7), client,
    )
    assert "29.08.2026 14:30 · qwen3 8b · v3" in event.message.edit_text.await_args.args[0]
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "ai:run:42:7:101"
    assert keyboard.inline_keyboard[-1][0].callback_data == "ai:latest:42:7:0"


async def test_opens_specific_saved_run_without_generation() -> None:
    event = callback()
    client = SimpleNamespace(get_llm_analysis_run=AsyncMock(return_value=analysis_payload()))
    await analysis_run(
        event, AnalysisCallback(action="run", match_id=42, tournament_id=7, run_id=101), client,
    )
    client.get_llm_analysis_run.assert_awaited_once_with(101)
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "ai:regenerate:42:7:101"
    assert keyboard.inline_keyboard[1][0].callback_data == "ai:history:42:7:0"


async def test_regenerate_creates_and_opens_new_run() -> None:
    event = callback()
    client = SimpleNamespace(
        regenerate_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=202)),
    )
    await regenerate_analysis(
        event,
        AnalysisCallback(action="regenerate", match_id=42, tournament_id=7, run_id=101),
        client,
    )
    client.regenerate_llm_analysis.assert_awaited_once_with(101)
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "ai:regenerate:42:7:202"


async def test_api_client_latest_404_has_distinct_error() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    http_client = httpx.AsyncClient(
        base_url="http://backend", transport=httpx.MockTransport(respond),
    )
    client = CS2EyeAPIClient("http://backend", client=http_client)
    try:
        try:
            await client.get_latest_llm_analysis(team_a_id=1, team_b_id=2, match_id=42)
        except CS2EyeNotFoundError as error:
            assert error.status_code == 404
        else:
            raise AssertionError("CS2EyeNotFoundError was not raised")
    finally:
        await http_client.aclose()


async def test_back_to_matches_reuses_navigation_snapshot() -> None:
    state = NavigationState()
    client = SimpleNamespace(
        get_tournament=AsyncMock(return_value={"id": 7, "name": "IEM Chengdu"}),
        get_tournament_matches=AsyncMock(return_value=[match_payload()]),
    )
    await tournament_matches(
        callback(user_id=501), TournamentCallback(tournament_id=7), client, state,
    )
    await back_to_matches(
        callback(user_id=501),
        NavigationCallback(destination="matches", tournament_id=7), client, state,
    )
    client.get_tournament.assert_awaited_once_with(7)
    client.get_tournament_matches.assert_awaited_once_with(7)


async def test_open_tournament_reuses_selected_item_from_tournaments_screen() -> None:
    state = NavigationState()
    first_event = callback(user_id=504)
    tournament = {
        "id": 7, "name": "IEM Chengdu",
        "start_date": "2099-05-01", "end_date": "2099-05-10",
    }
    client = SimpleNamespace(
        get_tournaments=AsyncMock(return_value=[tournament]),
        get_tournament=AsyncMock(side_effect=AssertionError("redundant request")),
        get_tournament_matches=AsyncMock(return_value=[match_payload()]),
    )
    await tournaments(first_event, client, state)
    tournament_event = callback(user_id=504)
    await tournament_matches(
        tournament_event, TournamentCallback(tournament_id=7), client, state,
    )
    client.get_tournament.assert_not_awaited()
    client.get_tournament_matches.assert_awaited_once_with(7)
    assert "IEM Chengdu" in tournament_event.message.edit_text.await_args.args[0]


async def test_tournaments_response_cache_obeys_ttl() -> None:
    requests = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, request=request, json={"items": []})

    http_client = httpx.AsyncClient(
        base_url="http://backend", transport=httpx.MockTransport(respond),
    )
    client = CS2EyeAPIClient(
        "http://backend", client=http_client, tournaments_ttl=60,
    )
    try:
        with patch("cs2eye.bot.api_client.monotonic", side_effect=[100, 120, 161]):
            await client.get_tournaments()
            await client.get_tournaments()
            await client.get_tournaments()
        assert requests == 2
    finally:
        await http_client.aclose()


async def test_api_client_reuses_one_async_client_and_closes_owned_client() -> None:
    seen_clients: list[httpx.AsyncClient] = []

    async def fake_request(self: httpx.AsyncClient, *args: object, **kwargs: object):
        seen_clients.append(self)
        request = httpx.Request("GET", "http://backend/api/v1/tournaments")
        return httpx.Response(200, request=request, json={"items": []})

    with patch.object(httpx.AsyncClient, "request", new=fake_request):
        client = CS2EyeAPIClient("http://backend", tournaments_ttl=0)
        owned_client = client._client
        await client.get_tournaments()
        await client.get_tournaments()
        assert seen_clients == [owned_client, owned_client]
        await client.close()
        assert owned_client.is_closed


async def test_generate_replaces_session_analysis() -> None:
    state = NavigationState()
    event = callback(user_id=502)
    state.for_callback(event).analyses[42] = analysis_payload(run_id=101)
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        generate_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=202)),
        get_latest_llm_analysis=AsyncMock(),
    )
    data = AnalysisCallback(action="generate", match_id=42, tournament_id=7)
    await generate_analysis(event, data, client, state)
    reopened = callback(user_id=502)
    await latest_analysis(reopened, data, client, state)
    assert state.for_callback(reopened).analyses[42]["analysis_run_id"] == 202
    client.get_latest_llm_analysis.assert_not_awaited()


async def test_callback_is_answered_before_backend_request() -> None:
    event = callback(user_id=503)

    async def get_tournaments() -> list[dict]:
        event.answer.assert_awaited_once()
        return []

    await tournaments(
        event, SimpleNamespace(get_tournaments=AsyncMock(side_effect=get_tournaments)),
        NavigationState(),
    )


def test_maps_veto_formatter_is_compact_and_uses_backend_edges() -> None:
    match = match_payload() | {"veto": [
        {"team_name": "Aurora", "action": "ban", "map_name": "nuke"},
    ]}
    text = format_maps_veto(match, detail_context_payload())
    assert "Anubis — Aurora" in text
    assert "T: Aurora" in text
    assert "Dust2 — близко" in text
    assert "Inferno — M80" in text
    assert "Factual veto" in text and "Aurora: ban Nuke" in text
    assert "Aurora: Anubis — 59.1" in text


def test_form_formatter_uses_numeric_backend_values() -> None:
    text = format_form(detail_context_payload())
    assert "Турнир: 50.6 · матчей: 2" in text
    assert "Последние 60 дней: 49.1 · матчей: 5" in text
    assert "SoS: 80.7" in text
    assert "хорош" not in text.casefold()


def test_h2h_formatter_separates_organizations_and_current_rosters() -> None:
    text = format_h2h(detail_context_payload())
    assert "H2H организаций" in text and "Серии: 3" in text
    assert "H2H текущими составами" in text and "Серии: 1" in text


def test_h2h_formatter_explicitly_reports_no_current_roster_meetings() -> None:
    context = detail_context_payload()
    context["h2h"]["current_rosters"] = {
        "status": "no_meetings", "series_played": 0,
    }
    assert "Текущими составами команды не встречались" in format_h2h(context)


def test_roster_formatter_uses_roles_coach_and_backend_stability() -> None:
    text = format_rosters(detail_context_payload())
    assert "1. XANTARES (IGL)" in text
    assert "IGL: XANTARES" in text
    assert "Coach: ashhh" in text
    assert "Roster stability: 54.6" in text
    assert "s1n (stand-in)" in text


def test_detail_formatters_handle_empty_data() -> None:
    assert "Данных по форме пока нет" in format_form({"teams": {}})
    assert "Данные по составам пока недоступны" in format_rosters({"teams": {}})
    assert "Вероятные карты пока недоступны" in format_maps_veto({}, {})


async def test_match_detail_and_back_use_cached_card_without_backend_request() -> None:
    state = NavigationState()
    detail_event = callback(user_id=601)
    state.for_callback(detail_event).match_cards[42] = (
        match_payload(), detail_context_payload(),
    )
    client = SimpleNamespace(
        get_match=AsyncMock(), get_match_analysis_context=AsyncMock(),
    )
    await match_detail(
        detail_event, MatchDetailCallback(section="form", match_id=42, tournament_id=7),
        client, state,
    )
    back_event = callback(user_id=601)
    await match_card(back_event, MatchCallback(match_id=42, tournament_id=7), client, state)
    client.get_match.assert_not_awaited()
    client.get_match_analysis_context.assert_not_awaited()
    assert "ML prediction" in back_event.message.edit_text.await_args.args[0]


async def test_backend_error_for_one_detail_keeps_back_button() -> None:
    event = callback(user_id=602)
    client = SimpleNamespace(
        get_match=AsyncMock(side_effect=CS2EyeAPIError("down")),
    )
    await match_detail(
        event, MatchDetailCallback(section="h2h", match_id=42, tournament_id=7),
        client, NavigationState(),
    )
    assert event.message.edit_text.await_args.args[0] == ERROR_TEXT
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "← Назад к матчу"
