import pytest

from cs2eye.api.schemas.llm_quality import (
    LLMQualityConfiguration, LLMQualityReviewCreate,
)
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.llm_quality.dataset_v2 import DATASET_V2
from cs2eye.services.llm_quality_evaluation_service import LLMQualityEvaluationService
from cs2eye.services.match_llm_quality_evaluator import MatchLLMQualityEvaluator
from cs2eye.services.ollama_match_analysis_client import MatchAnalysisProviderResult


def output_for(case, *, generic=False):
    plan = case.explanation_plan_snapshot
    expected = plan.expected_winner
    expected_text = (
        f"По расчётам должна выиграть {expected.team_name} — {expected.win_probability:.0%}."
        if expected is not None else "Расчёт победителя недоступен."
    )
    if generic:
        return MatchLLMAnalysisV3(
            expected_winner_text=expected_text,
            conclusion_text="У команды есть преимущества.",
            form_text="У команды есть преимущества.",
            maps_text="У команды есть преимущества.",
            teamplay_text="У команды есть преимущества.",
            manual_text="У команды есть преимущества.",
        )
    maps = [item.map for item in plan.maps.key_map_edges]
    maps_text = (
        " ".join(
            f"На карте {edge.map} преимущество у {edge.favored_team_name} по внутренней аналитике."
            for edge in plan.maps.key_map_edges
        ) if maps else "Недостаточно надёжных данных для сравнения карт."
    )
    manual_notes = plan.manual_context.team_a or plan.manual_context.team_b
    manual_text = (
        "Ручные комментарии аналитика учтены при формировании раздела."
        if manual_notes else (plan.manual_context.empty_message or "Ручных комментариев по этому матчу нет.")
    )
    teamplay_text = (
        "Доступные различия в командной игре заранее отобраны внутренней аналитикой."
        if plan.teamplay.signals
        else (plan.teamplay.context_notes[0] if plan.teamplay.context_notes
              else "Надёжных различий в командной игре не найдено.")
    )
    form_text = (
        plan.form.context_notes[0] if plan.form.context_notes
        else "Турнирная форма команд описана по переданным результатам."
    )
    return MatchLLMAnalysisV3(
        expected_winner_text=expected_text,
        conclusion_text=(
            f"{plan.conclusion.favored_team_name or 'Ни одна из команд'} имеет преимущество "
            "по внутренней статистике CS2Eye; форма турнира рассматривается отдельно."
        ),
        form_text=form_text, maps_text=maps_text, teamplay_text=teamplay_text,
        manual_text=manual_text,
    )


def case(case_id):
    return next(x for x in DATASET_V2.cases if x.case_id == case_id)


def test_dataset_is_versioned_curated_and_cases_roundtrip():
    assert DATASET_V2.schema_version == "llm_quality_dataset.v2"
    assert 15 <= len(DATASET_V2.cases) <= 30
    assert len({x.case_id for x in DATASET_V2.cases}) == len(DATASET_V2.cases)
    assert type(DATASET_V2).model_validate_json(DATASET_V2.model_dump_json()) == DATASET_V2
    assert 4 <= sum(x.golden for x in DATASET_V2.cases) <= 10


def test_expected_scenarios_are_present():
    tags = {tag for item in DATASET_V2.cases for tag in item.tags}
    assert {
        "clear_favorite", "close_match", "map_advantage", "weak_map_sample",
        "teamplay_signals", "teamplay_empty", "manual_context", "weak_data",
        "insufficient_data", "tournament_just_started",
    } <= tags


def test_coverage_detects_must_mention_facts():
    item = case("map_advantage_relevant")
    evaluator = MatchLLMQualityEvaluator()
    valid = evaluator.evaluate(item, output_for(item))
    assert valid.coverage_score == 1
    missing = output_for(item).model_copy(update={"maps_text": "Недостаточно надёжных данных."})
    metrics = evaluator.evaluate(item, missing)
    assert metrics.coverage_score == 0
    assert not metrics.passed


def test_hallucination_fails_grounding():
    item = case("clear_favorite")
    output = output_for(item)
    output = output.model_copy(update={
        "maps_text": output.maps_text + " Команда также сильна на карте Vertigo.",
    })
    metrics = MatchLLMQualityEvaluator().evaluate(item, output)
    assert not metrics.grounding_pass and not metrics.passed


def test_repetition_generic_language_and_forbidden_wording_checks():
    item = case("manual_notes_both_teams")
    repeated = output_for(item).model_copy(update={
        "conclusion_text": "У команды есть преимущества.",
        "form_text": "У команды есть преимущества.",
    })
    metrics = MatchLLMQualityEvaluator().evaluate(item, repeated)
    assert metrics.repetition_score < 1
    assert metrics.specificity_score < .6
    english = output_for(item).model_copy(update={"conclusion_text": "This is an English output."})
    assert not MatchLLMQualityEvaluator().evaluate(item, english).language_pass
    betting = output_for(item).model_copy(update={"conclusion_text": "Я бы поставил на команду G2."})
    result = MatchLLMQualityEvaluator().evaluate(item, betting)
    assert not result.forbidden_wording_pass and not result.passed


def test_valid_concise_russian_output_scores_high():
    item = case("close_match")
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

    async def generate_fixed_plan(self, plan, **kwargs):
        item = next(self.cases)
        self.index += 1
        if self.index == self.fail_at:
            raise RuntimeError("provider unavailable")
        return MatchAnalysisProviderResult(analysis=output_for(item))

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_batch_saves_every_case_survives_provider_failure_and_aggregates():
    dataset = DATASET_V2.model_copy(update={"cases": DATASET_V2.cases[:3]})
    repository = MemoryRepository()
    provider = FakeProvider(dataset.cases, fail_at=2)
    config = LLMQualityConfiguration(provider="fake", model="fixed", prompt_version="match_analysis_prompt.v5")
    service = LLMQualityEvaluationService(repository, lambda _: provider)
    runs = await service.evaluate(dataset, config)
    assert len(runs) == len(dataset.cases) == len(repository.runs)
    assert runs[1].status == "failed" and provider.closed
    report = await service.report(dataset.schema_version, config, runs)
    assert report.cases == 3 and report.completed == 2


@pytest.mark.asyncio
async def test_config_dataset_reproducibility_comparison_and_manual_rating():
    dataset = DATASET_V2.model_copy(update={"cases": DATASET_V2.cases[:2]})
    repository = MemoryRepository()
    baseline = LLMQualityConfiguration(provider="fake", model="qwen3:8b", prompt_version="match_analysis_prompt.v5")
    service = LLMQualityEvaluationService(
        repository, lambda _: FakeProvider(dataset.cases),
    )
    first = await service.evaluate(dataset, baseline)
    assert [x.case_id for x in first] == [x.case_id for x in dataset.cases]
    repository.reviews.append((first[0].id, LLMQualityReviewCreate(
        rating="good", language_quality="good", clarity="good", usefulness="good",
    )))
    left = await service.report(dataset.schema_version, baseline, first)
    candidate = baseline.model_copy(update={"model": "qwen3:14b"})
    second = await LLMQualityEvaluationService(
        repository, lambda _: FakeProvider(dataset.cases),
    ).evaluate(dataset, candidate)
    right = await service.report(dataset.schema_version, candidate, second)
    comparison = service.compare(left, right)
    assert comparison.left.manual_good == 1
    assert "average_quality" in comparison.deltas
    assert candidate.prompt_version == baseline.prompt_version and candidate.model != baseline.model


def test_golden_cases_obey_structured_regression_constraints():
    evaluator = MatchLLMQualityEvaluator()
    for item in DATASET_V2.cases:
        if item.golden:
            metrics = evaluator.evaluate(item, output_for(item))
            assert metrics.coverage_score == 1
            assert metrics.grounding_pass


@pytest.mark.asyncio
async def test_optional_ollama_quality_evaluation():
    pytest.skip("Run explicitly through python -m cs2eye.llm_quality when Ollama is available")
