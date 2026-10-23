from datetime import UTC, date, datetime
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
            "prompt_version": "match_analysis_prompt.v5",
        },
        "explanation_plan": {
            "schema_version": "match_explanation_plan.v2",
            "expected_winner": {"team_id": 1, "team_name": "FURIA", "win_probability": .58},
        },
        "analysis": {
            "schema_version": "match_llm_analysis.v3",
            "expected_winner_text": "По расчётам должна выиграть FURIA — 58%.",
            "conclusion_text": "FURIA имеет небольшое преимущество по внутренней статистике CS2Eye.",
            "form_text": "Более сильная текущая форма поддерживает FURIA.",
            "maps_text": "Legacy может навязать борьбу на отдельных картах.",
            "teamplay_text": "Выборка данных пока небольшая.",
            "manual_text": "Ручных комментариев по этому матчу нет.",
        },
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
    assert "📌 <b>Итог</b>" in text


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
        get_match_summary=AsyncMock(return_value=context_payload()),
    )
    await match_card(event, MatchCallback(match_id=42, tournament_id=7), client)
    client.get_match_summary.assert_awaited_once_with(42)
    assert "Confidence: Medium" in event.message.edit_text.await_args.args[0]
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "ai:latest:42:7:0"
    assert any(button.text == "HE Kill" for row in keyboard.inline_keyboard for button in row)


async def test_he_kill_navigation_reuses_cached_match_context() -> None:
    state = NavigationState()
    first = callback(user_id=777)
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_match_summary=AsyncMock(return_value=context_payload()),
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
    client.get_match_summary.assert_awaited_once_with(42)
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


def test_llm_formatter_renders_expected_winner_and_fixed_sections() -> None:
    text = format_llm_analysis(analysis_payload())
    assert "🏆 <b>По расчётам должна выиграть FURIA — 58%</b>" in text
    assert "📌 <b>Итог</b>" in text
    assert "📈 <b>Форма</b>" in text
    assert "🗺 <b>Карты</b>" in text
    assert "🎯 <b>Тимплей и свинги</b>" in text
    assert "📝 <b>Ручная аналитика</b>" in text


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
    assert [button.text for row in keyboard.inline_keyboard for button in row] == [
        "← Назад",
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
    assert event.message.edit_text.await_args.args[0] == "AI-отчёт для этого матча пока не опубликован. Он будет доступен в день турнира."
    keyboard = event.message.edit_text.await_args.kwargs["reply_markup"]
    assert [button.text for row in keyboard.inline_keyboard for button in row] == ["← Назад"]


async def test_old_generate_button_only_opens_saved_report() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_latest_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=102)),
        generate_llm_analysis=AsyncMock(),
    )
    await generate_analysis(
        event, AnalysisCallback(action="generate", match_id=42, tournament_id=7), client,
    )
    client.generate_llm_analysis.assert_not_awaited()
    client.get_latest_llm_analysis.assert_awaited_once()
    assert "📌 <b>Итог</b>" in event.message.edit_text.await_args.args[0]


async def test_old_generate_button_does_not_generate_missing_report() -> None:
    event = callback()
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        get_latest_llm_analysis=AsyncMock(side_effect=CS2EyeNotFoundError("missing")),
        generate_llm_analysis=AsyncMock(),
    )
    await generate_analysis(
        event, AnalysisCallback(action="generate", match_id=42, tournament_id=7), client,
    )
    client.generate_llm_analysis.assert_not_awaited()
    assert event.message.edit_text.await_args.args[0] == "AI-отчёт для этого матча пока не опубликован. Он будет доступен в день турнира."


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
    assert keyboard.inline_keyboard[0][0].callback_data == "ai:history:42:7:0"


async def test_old_regenerate_button_cannot_generate() -> None:
    event = callback()
    client = SimpleNamespace(regenerate_llm_analysis=AsyncMock())
    await regenerate_analysis(
        event,
        AnalysisCallback(action="regenerate", match_id=42, tournament_id=7, run_id=101),
        client,
    )
    client.regenerate_llm_analysis.assert_not_awaited()
    event.answer.assert_awaited_once_with(
        "Перегенерация отчётов через Telegram отключена.", show_alert=True,
    )


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


async def test_back_to_matches_reloads_matches_instead_of_indefinite_snapshot() -> None:
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
    assert client.get_tournament_matches.await_count == 2


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


async def test_old_generate_button_refreshes_saved_session_analysis() -> None:
    state = NavigationState()
    event = callback(user_id=502)
    state.for_callback(event).analyses[42] = analysis_payload(run_id=101)
    client = SimpleNamespace(
        get_match=AsyncMock(return_value=match_payload()),
        generate_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=202)),
        get_latest_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=202)),
    )
    data = AnalysisCallback(action="generate", match_id=42, tournament_id=7)
    await generate_analysis(event, data, client, state)
    reopened = callback(user_id=502)
    await latest_analysis(reopened, data, client, state)
    assert state.for_callback(reopened).analyses[42]["analysis_run_id"] == 202
    assert client.get_latest_llm_analysis.await_count == 2
    client.generate_llm_analysis.assert_not_awaited()


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
    state.for_callback(detail_event).store_card(42, match_payload(), detail_context_payload())
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


async def test_expired_card_reloads_active_model_and_manual_input():
    state=NavigationState()
    event=callback(user_id=900)
    session=state.for_callback(event)
    session.store_card(42,match_payload(),context_payload())
    session.match_card_times[42]-=31
    fresh=context_payload()
    fresh['generated_at']='2026-10-13T11:00:00Z'
    fresh['prediction'].update(model_version='v13',team_a_probability=.69,team_b_probability=.31,
        manual_adjustment={'base_team_a_probability':.54,'impact_team_a_pp':15})
    client=SimpleNamespace(get_match=AsyncMock(return_value=match_payload()),
        get_match_summary=AsyncMock(return_value=fresh))
    await match_card(event,MatchCallback(match_id=42,tournament_id=7),client,state)
    text=event.message.edit_text.await_args.args[0]
    assert 'Модель: v13' in text and 'FURIA — 69%' in text
    assert 'Ручной анализ: FURIA +15.0 п.п.' in text
    assert '13.10.2026 11:00 UTC' in text
    client.get_match_summary.assert_awaited_once()


async def test_refresh_button_bypasses_even_fresh_card():
    state=NavigationState()
    event=callback(user_id=901)
    state.for_callback(event).store_card(42,match_payload(),context_payload())
    changed=context_payload()
    changed['prediction']['team_a_probability']=.8
    changed['prediction']['team_b_probability']=.2
    client=SimpleNamespace(get_match=AsyncMock(return_value=match_payload()),
        get_match_summary=AsyncMock(return_value=changed))
    await match_detail(event,MatchDetailCallback(section='refresh',match_id=42,tournament_id=7),client,state)
    assert 'FURIA — 80%' in event.message.edit_text.await_args.args[0]
    event.answer.assert_awaited_once()
    client.get_match_summary.assert_awaited_once()


async def test_latest_analysis_does_not_keep_a_cached_missing_or_old_run():
    state=NavigationState()
    event=callback(user_id=902)
    state.for_callback(event).analyses[42]=None
    client=SimpleNamespace(get_match=AsyncMock(return_value=match_payload()),
        get_latest_llm_analysis=AsyncMock(return_value=analysis_payload(run_id=202)))
    await latest_analysis(event,AnalysisCallback(action='latest',match_id=42,tournament_id=7),client,state)
    client.get_latest_llm_analysis.assert_awaited_once()
    assert state.for_callback(event).analyses[42]['analysis_run_id']==202


async def test_api_client_regenerates_with_new_context_and_long_analytics_timeout():
    seen=[]
    async def respond(request):
        seen.append(request)
        return httpx.Response(200,request=request,json={'analysis_run_id':202})
    async with httpx.AsyncClient(base_url='http://backend',transport=httpx.MockTransport(respond)) as http:
        client=CS2EyeAPIClient('http://backend',client=http,analytics_timeout=120)
        await client.get_match_analysis_context(team_a_id=1,team_b_id=2,as_of=datetime.now(UTC),match_id=42,tournament_id=7)
        assert seen[-1].extensions['timeout']['read']==120
        await client.regenerate_llm_analysis(101)
        import json
        body=json.loads(seen[-1].content)
        assert body['reuse_context'] is False and body['as_of']


def test_completed_match_card_distinguishes_current_forecast_from_archive():
    match=match_payload()|{'status':'completed','score':{'team_a':2,'team_b':0}}
    text=format_match_card(match,context_payload())
    assert 'Матч завершён · 2:0' in text
    assert 'не архив предматчевого прогноза' in text


def test_past_tournaments_order_and_missing_history_card():
    from cs2eye.bot.formatters import past_tournaments, format_past_match_card
    from cs2eye.bot.keyboards import main_menu_keyboard
    items = past_tournaments([{"id":1,"start_date":"2026-08-26","end_date":"2026-09-01"}, {"id":2,"name":"ESL Pro League Season 24","start_date":"2026-10-03","end_date":"2026-10-12"}, {"id":3,"start_date":"2026-10-20","end_date":"2026-11-01"}], today=date(2026,10,14))
    assert [item["id"] for item in items] == [2]
    assert any(button.text == "Прошлые турниры" for row in main_menu_keyboard().inline_keyboard for button in row)
    match = match_payload() | {"status":"completed", "score":{"team_a":2,"team_b":0}, "winner_team_id":1,
        "prediction_history_coverage":{"as_of":"2026-10-03","required_maps":3,"teams":[{"name":"1win","available_maps":0}]}}
    text = format_past_match_card(match, [])
    assert "Прогноз до матча не был сохранён" in text
    assert "1win: 0 карт" in text
    assert "Счёт: 2 : 0" in text


async def test_archived_navigation_and_saved_forecast_without_live_analysis():
    from cs2eye.bot.handlers import archived_tournaments
    state = NavigationState()
    event = callback(user_id=9991)
    match = match_payload() | {"status":"completed","score":{"team_a":2,"team_b":0},"winner_team_id":1}
    forecast = {"match_id":42,"source":"pre_match","versions":{"ml":"v12"},"created_at":"2026-10-02",
                "team_a":{"name":"Alpha"},"team_b":{"name":"Bravo"},"ml":{"predicted_winner":"Alpha","team_a_value":.7,"team_b_value":.3,"correct":True}}
    client = SimpleNamespace(get_tournaments=AsyncMock(return_value=[{"id":7,"name":"Cup","start_date":"2026-10-03","end_date":"2026-10-12"}]),
        get_tournament_matches=AsyncMock(return_value=[match, match | {"id":43,"status":"scheduled"}]),
        get_match=AsyncMock(return_value=match),get_saved_match_forecasts=AsyncMock(return_value=[forecast]),
        get_match_analysis_context=AsyncMock())
    await archived_tournaments(event,client,state)
    await tournament_matches(event,TournamentCallback(tournament_id=7),client,state)
    keyboard=event.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "match:42:7"
    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[-1][0].callback_data == "nav:past_tournaments:0"
    await match_card(event,MatchCallback(match_id=42,tournament_id=7),client,state)
    text=event.message.edit_text.await_args.args[0]
    assert "Alpha: 70.0%" in text
    assert "✓ Угадали" in text
    client.get_match_analysis_context.assert_not_awaited()


async def test_restart_command_clears_only_current_user_and_opens_menu():
    from cs2eye.bot.handlers import start
    state = NavigationState()
    user = state.for_user(101)
    user.past_tournaments = True
    user.analyses[42] = {"old": True}
    user.bot_messages.add((101, 5))
    other = state.for_user(202)
    other.analyses[43] = {"keep": True}
    other.bot_messages.add((202, 8))
    chat = SimpleNamespace(id=101, type="private")
    bot = SimpleNamespace(delete_message=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=101), bot=bot,
        answer=AsyncMock(side_effect=[SimpleNamespace(chat=chat,message_id=10), SimpleNamespace(chat=chat,message_id=11)]))
    await start(message, state)
    bot.delete_message.assert_awaited_once_with(101, 5)
    assert state.for_user(101).analyses == {}
    assert not state.for_user(101).past_tournaments
    assert state.for_user(101).bot_messages == {(101,10),(101,11)}
    assert state.for_user(202) is other
    assert other.analyses == {43:{"keep":True}}
    keyboard = message.answer.await_args_list[0].kwargs["reply_markup"]
    assert keyboard.is_persistent
    assert [button.text for button in keyboard.keyboard[0]] == ["/start"]


async def test_restart_button_handles_undeletable_message_and_private_chat_only():
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import DeleteMessage
    from cs2eye.bot.handlers import restart_navigation
    state = NavigationState()
    bot = SimpleNamespace(delete_message=AsyncMock(side_effect=TelegramBadRequest(method=DeleteMessage(chat_id=101,message_id=5),message="message can't be deleted")))
    chat = SimpleNamespace(id=101,type="private")
    message = SimpleNamespace(chat=chat,message_id=5,answer=AsyncMock(side_effect=[SimpleNamespace(chat=chat,message_id=10),SimpleNamespace(chat=chat,message_id=11)]))
    event = SimpleNamespace(from_user=SimpleNamespace(id=101),message=message,bot=bot,answer=AsyncMock())
    await restart_navigation(event,state)
    event.answer.assert_awaited_once()
    assert message.answer.await_count == 2
    assert state.for_user(101).bot_messages == {(101,10),(101,11)}
    state.track_message(state.for_user(101),SimpleNamespace(chat=SimpleNamespace(id=-1,type="group"),message_id=20))
    assert (-1,20) not in state.for_user(101).bot_messages


async def test_card_shows_navigation_before_forecast_and_loads_details_lazily():
    import asyncio
    state = NavigationState()
    event = callback(user_id=950)
    entered, release = asyncio.Event(), asyncio.Event()

    async def summary(match_id):
        entered.set()
        await release.wait()
        return context_payload()

    client = SimpleNamespace(get_match=AsyncMock(return_value=match_payload()),
        get_match_summary=AsyncMock(side_effect=summary),
        get_match_analysis_context=AsyncMock(return_value=context_payload()))
    task = asyncio.create_task(match_card(event, MatchCallback(match_id=42, tournament_id=7), client, state))
    await asyncio.wait_for(entered.wait(), 1)
    try:
        text = event.message.edit_text.await_args.args[0]
        assert 'Рассчитываю прогноз' in text
        assert event.message.edit_text.await_args.kwargs['reply_markup']
        client.get_match_analysis_context.assert_not_awaited()
        assert state.for_callback(event).fresh_card(42) is None
    finally:
        release.set()
        await task
    assert 'Confidence: Medium' in event.message.edit_text.await_args.args[0]
    assert state.for_callback(event).fresh_summary(42) is not None
    assert state.for_callback(event).fresh_card(42) is None
    await match_detail(event, MatchDetailCallback(section='he_kill', match_id=42, tournament_id=7), client, state)
    await match_detail(event, MatchDetailCallback(section='h2h', match_id=42, tournament_id=7), client, state)
    client.get_match_analysis_context.assert_awaited_once()
    client.get_match_summary.assert_awaited_once_with(42)


async def test_late_card_forecast_does_not_overwrite_open_detail():
    import asyncio
    state = NavigationState()
    event = callback(user_id=951)
    entered, release = asyncio.Event(), asyncio.Event()

    async def summary(match_id):
        entered.set()
        await release.wait()
        return context_payload()

    client = SimpleNamespace(get_match=AsyncMock(return_value=match_payload()),
        get_match_summary=AsyncMock(side_effect=summary),
        get_match_analysis_context=AsyncMock(return_value=context_payload()))
    task = asyncio.create_task(match_card(event, MatchCallback(match_id=42, tournament_id=7), client, state))
    await asyncio.wait_for(entered.wait(), 1)
    try:
        await match_detail(event, MatchDetailCallback(section='he_kill', match_id=42, tournament_id=7), client, state)
        detail_text = event.message.edit_text.await_args.args[0]
        assert 'HE Kill' in detail_text
    finally:
        release.set()
        await task
    assert event.message.edit_text.await_args.args[0] == detail_text
    assert event.message.edit_text.await_count == 2


async def test_summary_api_uses_light_endpoint():
    seen = []
    async def respond(request):
        seen.append(request)
        return httpx.Response(200, json=context_payload())
    async with httpx.AsyncClient(base_url='http://backend', transport=httpx.MockTransport(respond)) as http:
        client = CS2EyeAPIClient('http://backend', client=http)
        await client.get_match_summary(42)
    assert seen[0].url.path == '/api/v1/analysis/match-card-context'
    assert seen[0].url.params['match_id'] == '42'
