from copy import deepcopy

import pytest

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.prompts.match_analysis_v1 import PROMPT_VERSION as V1
from cs2eye.prompts.match_analysis_v2 import PROMPT_VERSION as V2
from cs2eye.prompts.match_analysis_v3 import PROMPT_VERSION as V3, build_user_input
from cs2eye.services.deterministic_match_explanation_builder import (
    DeterministicMatchExplanationBuilder,
)
from cs2eye.services.match_explanation_rules import probability_advantage
from cs2eye.services.match_llm_analysis_v2_validator import (
    MatchLLMAnalysisV2Validator, MatchLLMV2ValidationError,
)
from cs2eye.services.ollama_match_analysis_client import OllamaMatchAnalysisClient
from tests.test_match_analysis_context import full_context_payload


def source(mutator=None):
    payload = deepcopy(full_context_payload())
    if mutator:
        mutator(payload)
    return MatchAnalysisContext.model_validate(payload)


def aurora_g2():
    def mutate(payload):
        payload["teams"]["team_a"]["name"] = "Aurora"
        payload["teams"]["team_b"]["name"] = "G2"
        payload["prediction"].update({
            "team_a_probability": .4186, "team_b_probability": .5814,
            "confidence": .7465,
        })
        payload["matchup"].update({
            "team_a_score": 51.13, "team_b_score": 48.87, "reliability": .7465,
        })
        payload["data_quality"]["overall_status"] = "weak"
        payload["data_quality"]["warnings"] = ["Tournament form unavailable for team_a."]
    return source(mutate)


def wording(plan):
    def texts(items, attr):
        return {getattr(item, attr): (
            "По ручной заметке аналитика отмечен дополнительный фактор."
            if getattr(item, "source_kind", None) == "manual"
            else "Проверенный аналитический сигнал."
        ) for item in items}
    return MatchLLMAnalysisV2(
        summary="Предматчевый вывод основан на проверенных сигналах CS2Eye.",
        advantage_texts=texts(plan.advantages, "signal_id"),
        counter_argument_texts=texts(plan.counter_arguments, "signal_id"),
        contradiction_texts=texts(plan.contradictions, "contradiction_id"),
        risk_texts=texts(plan.risks, "risk_id"),
        limitation_texts=texts(plan.limitations, "limitation_id"),
    )


def test_same_context_always_produces_identical_plan():
    builder = DeterministicMatchExplanationBuilder()
    context = aurora_g2()
    assert builder.build(context).model_dump() == builder.build(context).model_dump()


def test_aurora_g2_plan_owns_conclusion_and_ml_matchup_conflict():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    assert plan.conclusion.favored_team == "team_b"
    assert plan.conclusion.advantage == "small"
    assert plan.conclusion.confidence == "low"
    assert plan.status == "limited"
    conflict = next(x for x in plan.contradictions if x.category == "ml_vs_matchup")
    assert (conflict.left_side, conflict.right_side) == ("team_b", "team_a")
    matchup_counter = next(x for x in plan.counter_arguments if x.category == "matchup")
    assert matchup_counter.side == "team_a"
    assert matchup_counter.evidence_refs == ["matchup"]


@pytest.mark.parametrize(("delta", "expected"), [
    ((.5, .5), "none"), ((.58, .42), "small"),
    ((.61, .39), "moderate"), ((.7, .3), "clear"),
])
def test_advantage_thresholds_are_deterministic(delta, expected):
    assert probability_advantage(*delta) == expected


def test_unreliable_and_tiny_map_signals_are_excluded():
    def mutate(payload):
        payload["map_matchups"][0]["team_a"].update({"reliability": .18, "sample_maps": 1})
        payload["map_matchups"][0]["team_b"].update({"reliability": .18, "sample_maps": 1})
    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    assert not any(item.signal_id.startswith("signal:map:mirage")
                   for item in (*plan.advantages, *plan.counter_arguments))


def test_missing_optional_leadership_reliability_does_not_break_plan():
    def mutate(payload):
        payload["teams"]["team_b"]["leadership"]["reliability"] = None

    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    assert not any(
        item.category == "leadership"
        for item in (*plan.advantages, *plan.counter_arguments)
    )


def test_reliable_factor_is_classified_relative_to_ml_favorite():
    plan = DeterministicMatchExplanationBuilder().build(source())
    assert all(item.side == plan.conclusion.favored_team for item in plan.advantages)
    assert all(item.side != plan.conclusion.favored_team for item in plan.counter_arguments)
    assert plan.advantages
    assert plan.counter_arguments


def test_weak_matchup_does_not_create_false_contradiction():
    def mutate(payload):
        payload["prediction"].update({"team_a_probability": .4, "team_b_probability": .6})
        payload["matchup"].update({"team_a_score": 60, "team_b_score": 40, "reliability": .1})
    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    assert not any(x.category == "ml_vs_matchup" for x in plan.contradictions)


def test_matchup_h2h_component_cannot_bypass_h2h_reliability_rule():
    def mutate(payload):
        payload["prediction"].update({"team_a_probability": .48, "team_b_probability": .52})
        payload["matchup"]["factors"].append({
            "factor_id": "matchup:h2h", "key": "h2h",
            "team_a_score": 64, "team_b_score": 36,
            "reliability": .37, "sample_size": 2,
        })
        payload["h2h"]["history_applicability"] = "low"
    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    assert not any(
        item.category == "h2h"
        for item in (*plan.advantages, *plan.counter_arguments)
    )


def test_near_neutral_strength_does_not_contradict_recent_form():
    def mutate(payload):
        payload["teams"]["team_a"]["team_strength"]["score"] = 52.42
        payload["teams"]["team_b"]["team_strength"]["score"] = 52.16
        payload["teams"]["team_a"]["form"].update({
            "recent_60d_score": 51.95, "recent_60d_reliability": .6667,
            "recent_60d_matches": 4,
        })
        payload["teams"]["team_b"]["form"].update({
            "recent_60d_score": 56.33, "recent_60d_reliability": .7999,
            "recent_60d_matches": 5,
        })
    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    assert not any(x.category == "strength_vs_form" for x in plan.contradictions)


def test_current_roster_h2h_is_preferred_and_conflict_is_detected():
    def mutate(payload):
        payload["h2h"]["history_applicability"] = "medium"
        payload["h2h"]["organizations"].update({
            "team_a_rating": 65, "team_b_rating": 35, "confidence": .8,
        })
        payload["h2h"]["current_rosters"].update({
            "team_a_rating": 35, "team_b_rating": 65, "confidence": .8,
            "series_played": 4,
        })
    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    h2h_signal = next(
        item for item in (*plan.advantages, *plan.counter_arguments)
        if item.category == "h2h"
    )
    assert h2h_signal.side == "team_b"
    assert h2h_signal.evidence_refs == ["h2h:current_rosters"]
    assert any(x.category == "organization_vs_roster_h2h" for x in plan.contradictions)


def test_overall_map_profile_can_conflict_with_reliable_relevant_maps():
    def mutate(payload):
        payload["matchup"]["factors"].append({
            "factor_id": "matchup:map_veto", "key": "map_veto",
            "team_a_score": 40, "team_b_score": 60, "reliability": .8,
            "sample_size": 8,
        })
        payload["map_matchups"][0]["matchup_score_team_a"] = 65
    plan = DeterministicMatchExplanationBuilder().build(source(mutate))
    assert any(x.category == "overall_vs_relevant_maps" for x in plan.contradictions)


def test_manual_direction_and_source_are_backend_owned():
    favorite_plan = DeterministicMatchExplanationBuilder().build(source())
    manual = next(x for x in favorite_plan.advantages if x.source_kind == "manual")
    assert manual.direction == "supports_favorite"
    def underdog(payload):
        payload["prediction"].update({"team_a_probability": .4, "team_b_probability": .6})
    underdog_plan = DeterministicMatchExplanationBuilder().build(source(underdog))
    manual = next(x for x in underdog_plan.counter_arguments if x.source_kind == "manual")
    assert manual.direction == "against_favorite"


def test_quality_warnings_become_typed_limitations_and_limits_hold():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    assert plan.limitations and plan.limitations[0].category == "tournament_form"
    assert len(plan.advantages) <= 5 and len(plan.counter_arguments) <= 5
    assert len(plan.contradictions) <= 3 and len(plan.risks) <= 5


def test_v2_is_text_only_and_rejects_unknown_or_missing_ids_and_numbers():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    schema = MatchLLMAnalysisV2.model_json_schema()["properties"]
    assert not {"favored_team", "confidence", "reliability"} & set(schema)
    validator = MatchLLMAnalysisV2Validator()
    valid = wording(plan)
    validator.validate(plan, valid)
    invalid = valid.model_copy(update={"advantage_texts": {"signal:999": "Новый тезис."}})
    with pytest.raises(MatchLLMV2ValidationError, match="unknown IDs"):
        validator.validate(plan, invalid)
    if plan.advantages:
        high = next((x for x in plan.advantages if x.importance == "high"), None)
        if high:
            missing = valid.model_copy(update={
                "advantage_texts": {k: v for k, v in valid.advantage_texts.items()
                                    if k != high.signal_id},
            })
            with pytest.raises(MatchLLMV2ValidationError, match="misses required IDs"):
                validator.validate(plan, missing)
    numbered = valid.model_copy(update={"summary": "Вероятность составляет 99 процентов."})
    with pytest.raises(MatchLLMV2ValidationError, match="new number"):
        validator.validate(plan, numbered)
    rounded = valid.model_copy(update={
        "summary": "Вероятность фаворита по модели составляет 58,1%.",
    })
    validator.validate(plan, rounded)
    tournament_plan = plan.model_copy(update={
        "supporting_context": plan.supporting_context.model_copy(update={
            "tournament": "BLAST Open Porto 2026",
        }),
    })
    tournament_text = valid.model_copy(update={
        "summary": "Матч проходит в рамках BLAST Open Porto 2026.",
    })
    validator.validate(tournament_plan, tournament_text)
    entity = valid.model_copy(update={"summary": "Фаворитом считается Vitality."})
    with pytest.raises(MatchLLMV2ValidationError, match="English prose"):
        validator.validate(plan, entity)
    reversed_summary = valid.model_copy(update={"summary": "Aurora является фаворитом матча."})
    with pytest.raises(MatchLLMV2ValidationError, match="reverses deterministic conclusion"):
        validator.validate(plan, reversed_summary)
    valid_comparison = valid.model_copy(update={
        "summary": "G2 предпочтительнее Aurora, но преимущество фаворита невелико.",
    })
    validator.validate(plan, valid_comparison)


def test_v3_prompt_receives_plan_not_raw_context_and_versions_remain_available():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    prompt = build_user_input(plan)
    assert "match_explanation_plan.v1" in prompt
    assert "recent_series_evidence" not in prompt
    assert (V1, V2, V3) == (
        "match_analysis_prompt.v1", "match_analysis_prompt.v2", "match_analysis_prompt.v3",
    )


def test_v3_language_repair_explicitly_requires_all_text_in_russian():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    prompt = build_user_input(
        plan,
        repair_errors=(
            "human-readable text must be Russian",
            "English prose is not allowed: unsupported words ['the', 'team']",
        ),
        previous_analysis=wording(plan),
    )

    assert "полностью перепиши summary и все значения в секциях *_texts" in prompt
    assert "Каждое текстовое поле должно содержать осмысленное предложение кириллицей" in prompt
    assert "Текст должен быть на русском языке; английская проза запрещена." in prompt
    assert "['the', 'team']" in prompt
    assert "human-readable text must be Russian" not in prompt
    assert "Предыдущий ответ:" in prompt


def test_v3_output_schema_allows_only_plan_ids_and_requires_high_items():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    schema = OllamaMatchAnalysisClient._plan_output_schema(plan)
    advantage = schema["properties"]["advantage_texts"]
    assert advantage["additionalProperties"] is False
    assert set(advantage["properties"]) == {item.signal_id for item in plan.advantages}
    assert set(advantage["required"]) == {
        item.signal_id for item in plan.advantages if item.importance == "high"
    }


def test_v3_validator_allows_snake_case_plan_terms_rendered_with_spaces():
    plan = DeterministicMatchExplanationBuilder().build(aurora_g2())
    valid = wording(plan)
    advantage = plan.advantages[0]
    advantage.facts[0].values["metric"] = "force_buy"
    valid.advantage_texts[advantage.signal_id] = (
        "G2 имеет преимущество в фазе force buy."
    )

    MatchLLMAnalysisV2Validator().validate(plan, valid)
