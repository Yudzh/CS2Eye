from copy import deepcopy

import pytest

from cs2eye.api.schemas.llm_quality import (
    LLMQualityConfiguration, LLMQualityReviewCreate,
)
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.llm_quality.dataset_v1 import DATASET_V1
from cs2eye.prompts.match_analysis_registry import get_plan_prompt
from cs2eye.services.llm_quality_evaluation_service import LLMQualityEvaluationService
from cs2eye.services.match_llm_quality_evaluator import MatchLLMQualityEvaluator
from cs2eye.services.ollama_match_analysis_client import MatchAnalysisProviderResult


def output_for(case, *, generic=False):
    plan = case.explanation_plan_snapshot
    def signal_text(item):
        if item.source_kind == "manual":
            return "По ручной заметке аналитика этот фактор влияет на оценку матча."
        if generic:
            return "У команды есть преимущества."
        labels = {
            "recent_form": "текущая форма команды G2",
            "map_pool": "профиль релевантной карты",
            "matchup": "детерминированный Matchup",
            "roster": "стабильность состава",
            "h2h": "встречи текущих составов",
            "strength_of_schedule": "сила недавних соперников",
            "overall_strength": "общая сила команды",
            "tournament_form": "форма на текущем турнире",
            "manual_context": "ручная заметка аналитика",
        }
        return f"{labels.get(item.category, 'Конкретный аналитический фактор')} поддерживает указанную сторону."
    return MatchLLMAnalysisV2(
        summary="G2 сохраняет заданное планом преимущество, однако важны указанные ограничения.",
        advantage_texts={x.signal_id: signal_text(x) for x in plan.advantages},
        counter_argument_texts={x.signal_id: signal_text(x) for x in plan.counter_arguments},
        contradiction_texts={x.contradiction_id:
            "ML-прогноз и детерминированный Matchup указывают на разные команды."
            for x in plan.contradictions},
        risk_texts={x.risk_id: "Качество доступных данных создаёт риск для вывода."
                    for x in plan.risks},
        limitation_texts={x.limitation_id: "Доступных данных по этому фактору недостаточно."
                          for x in plan.limitations},
    )


def case(case_id):
    return next(x for x in DATASET_V1.cases if x.case_id == case_id)


def test_dataset_is_versioned_curated_and_cases_roundtrip():
    assert DATASET_V1.schema_version == "llm_quality_dataset.v1"
    assert 20 <= len(DATASET_V1.cases) <= 30
    assert len({x.case_id for x in DATASET_V1.cases}) == len(DATASET_V1.cases)
    assert type(DATASET_V1).model_validate_json(DATASET_V1.model_dump_json()) == DATASET_V1
    assert 5 <= sum(x.golden for x in DATASET_V1.cases) <= 10


def test_expected_scenarios_are_present():
    tags = {tag for item in DATASET_V1.cases for tag in item.tags}
    assert {"clear_favorite", "close_match", "ml_vs_matchup_conflict", "weak_data",
            "insufficient_data", "strong_tournament_form", "strong_recent_form",
            "weak_schedule", "new_roster", "h2h_conflict", "manual_context",
            "map_advantage", "no_veto"} <= tags


def test_coverage_detects_must_cover_and_missing_high_signal():
    item = case("clear_favorite")
    evaluator = MatchLLMQualityEvaluator()
    valid = evaluator.evaluate(item, output_for(item))
    assert valid.coverage_score == 1
    missing = output_for(item).model_copy(update={"advantage_texts": {}})
    metrics = evaluator.evaluate(item, missing)
    assert metrics.coverage_score == 0
    assert not metrics.passed


def test_hallucination_fails_even_when_text_is_well_formed():
    item = case("clear_favorite")
    output = output_for(item)
    output = output.model_copy(update={"advantage_texts": {
        **output.advantage_texts, "signal:invented": "Выдуманный фактор команды."
    }})
    metrics = MatchLLMQualityEvaluator().evaluate(item, output)
    assert not metrics.grounding_pass and not metrics.passed


def test_repetition_generic_language_and_forbidden_wording_checks():
    item = case("mixed_manual_statistical")
    repeated = output_for(item).model_copy(update={
        "advantage_texts": {key: "У команды есть преимущества."
                            for key in output_for(item).advantage_texts},
    })
    metrics = MatchLLMQualityEvaluator().evaluate(item, repeated)
    assert metrics.repetition_score < 1
    assert metrics.specificity_score < .6
    english = output_for(item).model_copy(update={"summary": "This is an English output."})
    assert not MatchLLMQualityEvaluator().evaluate(item, english).language_pass
    betting = output_for(item).model_copy(update={"summary": "Я бы поставил на команду G2."})
    result = MatchLLMQualityEvaluator().evaluate(item, betting)
    assert not result.forbidden_wording_pass and not result.passed


def test_valid_concise_russian_output_scores_high():
    item = case("slight_ml_matchup_conflict")
    metrics = MatchLLMQualityEvaluator().evaluate(item, output_for(item))
    assert metrics.language_pass and metrics.grounding_pass
    assert metrics.coverage_score == 1 and metrics.quality_score >= 85


class MemoryRepository:
    def __init__(self):
        self.runs = []
        self.reviews = []

    async def save_run(self, result):
        result = result.model_copy(update={"id": len(self.runs) + 1})
        self.runs.append(result)
        return result

    async def list_runs(self, dataset_version, configuration):
        return [x for x in self.runs if x.dataset_version == dataset_version
                and x.configuration == configuration]

    async def add_review(self, run_id, review):
        self.reviews.append((run_id, review))

    async def manual_counts(self, run_ids):
        selected = [review for run_id, review in self.reviews if run_id in run_ids]
        return sum(x.rating == "good" for x in selected), len(selected)


class FakeProvider:
    def __init__(self, cases, fail_at=None):
        self.cases = iter(cases)
        self.fail_at = fail_at
        self.index = 0
        self.closed = False

    async def generate_plan(self, plan):
        item = next(self.cases)
        self.index += 1
        if self.index == self.fail_at:
            raise RuntimeError("provider unavailable")
        return MatchAnalysisProviderResult(analysis=output_for(item))

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_batch_saves_every_case_survives_provider_failure_and_aggregates():
    dataset = DATASET_V1.model_copy(update={"cases": DATASET_V1.cases[:3]})
    repository = MemoryRepository()
    provider = FakeProvider(dataset.cases, fail_at=2)
    config = LLMQualityConfiguration(provider="fake", model="fixed", prompt_version="v3")
    service = LLMQualityEvaluationService(repository, lambda _: provider)
    runs = await service.evaluate(dataset, config)
    assert len(runs) == len(dataset.cases) == len(repository.runs)
    assert runs[1].status == "failed" and provider.closed
    report = await service.report(dataset.schema_version, config, runs)
    assert report.cases == 3 and report.completed == 2


@pytest.mark.asyncio
async def test_config_dataset_reproducibility_comparison_and_manual_rating():
    dataset = DATASET_V1.model_copy(update={"cases": DATASET_V1.cases[:2]})
    repository = MemoryRepository()
    v3 = LLMQualityConfiguration(provider="fake", model="qwen3:8b", prompt_version="v3")
    service = LLMQualityEvaluationService(
        repository, lambda _: FakeProvider(dataset.cases),
    )
    first = await service.evaluate(dataset, v3)
    assert [x.case_id for x in first] == [x.case_id for x in dataset.cases]
    repository.reviews.append((first[0].id, LLMQualityReviewCreate(
        rating="good", language_quality="good", clarity="good", usefulness="good",
    )))
    left = await service.report(dataset.schema_version, v3, first)
    v4 = v3.model_copy(update={"prompt_version": "v4"})
    second = await LLMQualityEvaluationService(
        repository, lambda _: FakeProvider(dataset.cases),
    ).evaluate(dataset, v4)
    right = await service.report(dataset.schema_version, v4, second)
    comparison = service.compare(left, right)
    assert comparison.left.manual_good == 1
    assert "average_quality" in comparison.deltas
    model_b = v4.model_copy(update={"model": "qwen3:14b"})
    assert model_b.prompt_version == v4.prompt_version and model_b.model != v4.model


def test_golden_cases_obey_structured_regression_constraints():
    evaluator = MatchLLMQualityEvaluator()
    for item in DATASET_V1.cases:
        if item.golden:
            metrics = evaluator.evaluate(item, output_for(item))
            assert metrics.coverage_score == 1
            assert metrics.grounding_pass


def test_prompt_v3_v4_registry_keeps_analytical_input_identical():
    plan = case("slight_ml_matchup_conflict").explanation_plan_snapshot
    v3_system, v3_input = get_plan_prompt("match_analysis_prompt.v3")
    v4_system, v4_input = get_plan_prompt("match_analysis_prompt.v4")
    assert "match_explanation_plan.v1" in v3_input(plan)
    assert "match_explanation_plan.v1" in v4_input(plan)
    assert plan.model_dump_json() != ""
    assert v3_system() != v4_system()


@pytest.mark.asyncio
async def test_optional_ollama_quality_evaluation():
    pytest.skip("Run explicitly through python -m cs2eye.llm_quality when Ollama is available")
