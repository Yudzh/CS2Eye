from copy import deepcopy

import pytest

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.bot.formatters import format_llm_analysis
from cs2eye.prompts.match_analysis_v5 import PROMPT_VERSION, build_system_prompt
from cs2eye.services.deterministic_match_explanation_builder_v2 import (
    DeterministicMatchExplanationBuilderV2,
)
from cs2eye.services.match_llm_analysis_v3_validator import (
    MatchLLMAnalysisV3Validator, MatchLLMV3ValidationError,
)
from cs2eye.services.match_llm_analysis_run_service import _compatible_v2_plan_snapshot
from cs2eye.services.match_llm_analysis_service import MatchLLMAnalysisService
from cs2eye.services.ollama_match_analysis_client import OllamaMatchAnalysisClient
from tests.test_match_analysis_context import full_context_payload


def context(mutator=None):
    payload = deepcopy(full_context_payload())
    if mutator: mutator(payload)
    return MatchAnalysisContext.model_validate(payload)


def plan(mutator=None):
    return DeterministicMatchExplanationBuilderV2().build(context(mutator))


def wording(source_plan):
    a, b = source_plan.conclusion.team_a_name, source_plan.conclusion.team_b_name
    favorite = a if source_plan.conclusion.favored_team == "team_a" else b
    maps = [item.map for item in source_plan.maps.key_map_edges]
    map_text = f"Ключевая карта {maps[0]} заранее определена внутренней аналитикой." if maps else "Недостаточно надёжных данных для сравнения карт."
    return MatchLLMAnalysisV3(
        expected_winner_text=(
            f"По расчётам должна выиграть {source_plan.expected_winner.team_name} — "
            f"{source_plan.expected_winner.win_probability:.0%}."
            if source_plan.expected_winner else "Расчёт победителя недоступен."
        ),
        conclusion_text=f"{favorite} имеет преимущество по внутренней статистике CS2Eye; турнирная форма рассматривается отдельно.",
        form_text="Турнирная форма описана только по переданным результатам команд.",
        maps_text=map_text,
        teamplay_text="Доступные различия в командной игре заранее отобраны внутренней аналитикой.",
        manual_text="Ручных комментариев аналитика по этому матчу нет.",
    )


def test_fixed_plan_has_five_sections_and_is_deterministic():
    first, second = plan(), plan()
    assert first.model_dump() == second.model_dump()
    assert set(first.model_dump()) == {
        "schema_version", "context_schema_version", "expected_winner", "conclusion", "form",
        "maps", "teamplay", "manual_context",
    }
    assert first.schema_version == "match_explanation_plan.v2"


def test_early_v2_snapshot_without_display_names_remains_readable():
    source_context = context()
    snapshot = plan().model_dump(mode="json")
    snapshot.pop("expected_winner")
    snapshot["conclusion"].pop("favored_team_name")
    snapshot["form"]["comparison"].pop("favored_team_name")
    for edge in snapshot["maps"]["key_map_edges"]:
        edge.pop("favored_team_name")
        for reason in edge["reasons"]:
            reason.pop("side_name")
    for signal in snapshot["teamplay"]["signals"]:
        signal.pop("side_name")

    compatible = _compatible_v2_plan_snapshot(
        snapshot, source_context.model_dump(mode="json"),
    )
    restored = MatchExplanationPlanV2.model_validate(compatible)
    assert restored.conclusion.favored_team_name in {
        source_context.teams.team_a.name, source_context.teams.team_b.name,
    }


def test_expected_winner_comes_only_from_ml_team_a_probability():
    def team_a(payload):
        payload["prediction"].update({
            "status": "available", "team_a_probability": .57,
            "team_b_probability": .43,
        })
    result = plan(team_a)
    expected = result.expected_winner
    assert expected is not None
    assert expected.team_id == context(team_a).teams.team_a.id
    assert expected.team_name == context(team_a).teams.team_a.name
    assert expected.win_probability == .57


def test_expected_winner_uses_team_b_probability_when_higher():
    def team_b(payload):
        payload["prediction"].update({
            "status": "available", "team_a_probability": .43,
            "team_b_probability": .57,
        })
    result = plan(team_b)
    assert result.expected_winner is not None
    assert result.expected_winner.team_id == context(team_b).teams.team_b.id
    assert result.expected_winner.win_probability == .57


def test_expected_winner_is_unavailable_without_ml_prediction():
    def unavailable(payload):
        payload["prediction"].update({
            "status": "not_available", "team_a_probability": None,
            "team_b_probability": None,
        })
    assert plan(unavailable).expected_winner is None


def test_v3_validator_rejects_changed_expected_winner() -> None:
    source_plan = plan()
    valid = wording(source_plan)
    opponent = source_plan.conclusion.team_b_name
    changed = valid.model_copy(update={
        "expected_winner_text": f"По расчётам должна выиграть {opponent} — 57%.",
    })
    with pytest.raises(MatchLLMV3ValidationError, match="expected winner"):
        MatchLLMAnalysisV3Validator().validate(source_plan, changed)


def test_old_v3_analysis_without_expected_winner_field_is_readable() -> None:
    payload = wording(plan()).model_dump(mode="json")
    payload.pop("expected_winner_text")
    assert MatchLLMAnalysisV3.model_validate(payload).expected_winner_text is None


def test_new_llm_output_schema_requires_expected_winner() -> None:
    schema = OllamaMatchAnalysisClient._fixed_plan_output_schema()
    assert "expected_winner_text" in schema["required"]


def test_fixed_analysis_normalizes_deterministic_winner_and_manual_label() -> None:
    source_plan = plan()
    changed = wording(source_plan).model_copy(update={
        "expected_winner_text": "Другая команда должна выиграть — 1%.",
        "manual_text": "Игрок находится в хорошей форме.",
    })
    normalized = MatchLLMAnalysisService._normalize_fixed_analysis(source_plan, changed)
    assert source_plan.expected_winner is not None
    assert source_plan.expected_winner.team_name in normalized.expected_winner_text
    assert f"{source_plan.expected_winner.win_probability:.2%}" in normalized.expected_winner_text
    assert normalized.manual_text.startswith("Ручные комментарии аналитика:")
    MatchLLMAnalysisV3Validator().validate(source_plan, normalized)


def test_favorite_and_internal_statistics_basis_are_backend_owned():
    result = plan()
    expected = "team_a" if context().prediction.team_a_probability > context().prediction.team_b_probability else "team_b"
    assert result.conclusion.favored_team == expected
    assert "внутренней статистике CS2Eye" in result.conclusion.internal_statistics_disclaimer


def test_first_tournament_match_reports_no_form_instead_of_fallback():
    def mutate(payload):
        for side in ("team_a", "team_b"):
            payload["teams"][side]["form"].update({
                "tournament_matches": 0, "tournament_form_score": None,
                "tournament_reliability": None,
            })
            for item in payload["recent_series_evidence"][side]:
                item["current_tournament"] = False
    result = plan(mutate)
    assert result.form.state == "not_started"
    assert "Турнир только начинается" in result.form.context_notes[0]
    # A recent-60d or previous-tournament fallback would let a "strong form" claim leak
    # into a section whose own note says the teams have no tournament form yet.
    assert result.form.team_a.fallback == "none"
    assert result.form.team_a.score is None
    assert result.form.team_a.form_level == "unknown"
    assert result.form.team_b.fallback == "none"


def test_current_tournament_and_mixed_availability_states():
    def current(payload):
        for side in ("team_a", "team_b"):
            payload["teams"][side]["form"]["tournament_matches"] = 2
    assert plan(current).form.state == "current_tournament"
    def mixed(payload):
        payload["teams"]["team_a"]["form"] = {
            **payload["teams"]["team_a"]["form"], "tournament_matches": 2,
        }
        payload["teams"]["team_b"]["form"] = {
            **payload["teams"]["team_b"]["form"], "tournament_matches": 0,
        }
    result = plan(mixed)
    assert result.form.state == "mixed_availability"
    assert result.form.context_notes


def test_maps_are_selected_by_backend_and_low_sample_is_excluded():
    result = plan()
    assert len(result.maps.team_a.strong_maps) <= 3
    assert len(result.maps.team_b.weak_maps) <= 3
    def low_sample(payload):
        for item in payload["map_matchups"]:
            item["team_a"].update({"map_strength": 99, "reliability": .99, "sample_maps": 1})
    result = plan(low_sample)
    assert not result.maps.team_a.strong_maps


@pytest.mark.parametrize(("metric", "reason"), [
    ("ct_side", "ct_side"), ("trade", "trading"), ("full_buy", "full_buy"),
])
def test_key_map_edge_has_deterministic_reason(metric, reason):
    def mutate(payload):
        item = payload["map_matchups"][0]
        item["matchup_score_team_a"] = 65
        item["team_a"].update({"map_strength": 70, "reliability": .9, "sample_maps": 8})
        item["team_b"].update({"map_strength": 35, "reliability": .9, "sample_maps": 8})
        item["key_edges"] = [{
            "evidence_id": f"map:{item['map']}:{metric}", "metric": metric,
            "favored_team": "team_a", "strength": "clear", "reliability": .9,
        }]
    result = plan(mutate)
    edge = next(item for item in result.maps.key_map_edges if item.favored_team == "team_a")
    assert reason in {item.type for item in edge.reasons}


def test_teamplay_is_limited_and_weak_signals_are_excluded():
    def mutate(payload):
        metrics = ["ct_side", "t_side", "opening", "trade", "clutch", "postplant", "retake"]
        item = payload["map_matchups"][0]
        item["key_edges"] = [{
            "evidence_id": f"map:{item['map']}:{metric}", "metric": metric,
            "favored_team": "team_a", "strength": "clear" if index else "small",
            "reliability": .9,
        } for index, metric in enumerate(metrics)]
    result = plan(mutate)
    assert 1 <= len(result.teamplay.signals) <= 5
    assert all(item.strength != "small" for item in result.teamplay.signals)


def test_manual_notes_exist_only_in_manual_section_and_empty_state_is_explicit():
    result = plan()
    note_ids = {item.note_id for item in (*result.manual_context.team_a, *result.manual_context.team_b)}
    assert all(note_id not in signal.signal_id for note_id in note_ids for signal in result.teamplay.signals)
    def empty(payload):
        payload["manual_context"]["team_a"] = []
        payload["manual_context"]["team_b"] = []
    assert plan(empty).manual_context.empty_message == "Ручных комментариев по этому матчу нет."


def test_v3_validator_rejects_new_map_cross_section_and_reversed_conclusion():
    source_plan = plan()
    validator = MatchLLMAnalysisV3Validator()
    valid = wording(source_plan)
    validator.validate(source_plan, valid)
    with pytest.raises(MatchLLMV3ValidationError, match="unknown maps"):
        validator.validate(source_plan, valid.model_copy(update={"maps_text": "У команды сильная карта Vertigo."}))
    known_map = source_plan.maps.key_map_edges[0].map
    with pytest.raises(MatchLLMV3ValidationError, match="map facts"):
        validator.validate(source_plan, valid.model_copy(update={"form_text": f"Форма команды зависит от карты {known_map}."}))
    opponent = source_plan.conclusion.team_b_name if source_plan.conclusion.favored_team == "team_a" else source_plan.conclusion.team_a_name
    with pytest.raises(MatchLLMV3ValidationError, match="reverses"):
        validator.validate(source_plan, valid.model_copy(update={"conclusion_text": f"Преимущество имеет {opponent} по внутренней статистике CS2Eye."}))
    with pytest.raises(MatchLLMV3ValidationError, match="reverses"):
        validator.validate(source_plan, valid.model_copy(update={"conclusion_text": f"CS2Eye выбрала фаворита, однако ML-модель прогнозирует победу {opponent}."}))
    edge = source_plan.maps.key_map_edges[0]
    edge_opponent = source_plan.maps.team_b.team_name if edge.favored_team == "team_a" else source_plan.maps.team_a.team_name
    with pytest.raises(MatchLLMV3ValidationError, match="reverses edge"):
        validator.validate(source_plan, valid.model_copy(update={"maps_text": f"На карте {edge.map} {edge_opponent} имеет явное преимущество."}))


def test_v3_validator_keeps_opposite_map_edges_separate_at_semicolon():
    source_plan = plan()
    first = source_plan.maps.key_map_edges[0]
    opposite_side = "team_b" if first.favored_team == "team_a" else "team_a"
    opposite_name = (
        source_plan.maps.team_b.team_name
        if opposite_side == "team_b" else source_plan.maps.team_a.team_name
    )
    other_map = "inferno" if first.map != "inferno" else "anubis"
    opposite = first.model_copy(update={
        "map": other_map, "favored_team": opposite_side,
        "favored_team_name": opposite_name,
    })
    source_plan = source_plan.model_copy(update={
        "maps": source_plan.maps.model_copy(update={
            "key_map_edges": [first, opposite],
        }),
    })
    first_name = source_plan.maps.team_a.team_name if first.favored_team == "team_a" else source_plan.maps.team_b.team_name
    analysis = wording(source_plan).model_copy(update={
        "maps_text": (
            f"На карте {first.map} преимущество у {first_name}, а "
            f"на карте {opposite.map} преимущество у {opposite_name}."
        ),
    })
    MatchLLMAnalysisV3Validator().validate(source_plan, analysis)


def test_v3_has_identical_output_fields_prompt_v5_and_fixed_telegram_headers():
    source_plan = plan()
    analysis = wording(source_plan)
    assert list(analysis.model_dump()) == [
        "schema_version", "explanation_plan_version", "expected_winner_text", "conclusion_text", "form_text",
        "maps_text", "teamplay_text", "manual_text",
    ]
    assert PROMPT_VERSION == "match_analysis_prompt.v5"
    assert "ровно шесть текстовых полей" in build_system_prompt()
    rendered = format_llm_analysis({"analysis": analysis.model_dump(), "status": "completed"})
    for title in ("📌 <b>Итог</b>", "📈 <b>Форма</b>", "🗺 <b>Карты</b>", "🎯 <b>Тимплей и свинги</b>", "📝 <b>Ручная аналитика</b>"):
        assert title in rendered
