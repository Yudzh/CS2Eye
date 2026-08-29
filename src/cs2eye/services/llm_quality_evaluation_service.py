from cs2eye.api.schemas.llm_quality import (
    LLMQualityAggregateReport, LLMQualityComparison, LLMQualityConfiguration,
    LLMQualityDataset, LLMQualityRunResult,
)
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.services.match_llm_quality_evaluator import MatchLLMQualityEvaluator


class LLMQualityEvaluationService:
    def __init__(self, repository, provider_factory, evaluator=None):
        self.repository = repository
        self.provider_factory = provider_factory
        self.evaluator = evaluator or MatchLLMQualityEvaluator()

    async def evaluate(self, dataset: LLMQualityDataset,
                       configuration: LLMQualityConfiguration):
        provider = self.provider_factory(configuration)
        results = []
        try:
            for case in dataset.cases:
                try:
                    response = await provider.generate_plan(case.explanation_plan_snapshot)
                    if not isinstance(response.analysis, MatchLLMAnalysisV2):
                        raise TypeError("provider returned non-v2 output")
                    metrics = self.evaluator.evaluate(case, response.analysis)
                    result = LLMQualityRunResult(
                        case_id=case.case_id, dataset_version=dataset.schema_version,
                        configuration=configuration,
                        explanation_plan_snapshot=case.explanation_plan_snapshot,
                        llm_output_snapshot=response.analysis,
                        deterministic_metrics=metrics, quality_score=metrics.quality_score,
                        status="completed" if metrics.passed else "failed",
                        error_code=None if metrics.passed else "quality_checks_failed",
                    )
                except Exception as error:  # one provider failure must not stop a batch
                    result = LLMQualityRunResult(
                        case_id=case.case_id, dataset_version=dataset.schema_version,
                        configuration=configuration,
                        explanation_plan_snapshot=case.explanation_plan_snapshot,
                        status="failed", error_code=getattr(error, "kind", None)
                        or error.__class__.__name__,
                    )
                results.append(await self.repository.save_run(result))
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                await close()
        return results

    async def report(self, dataset_version, configuration, runs=None):
        runs = runs or await self.repository.list_runs(dataset_version, configuration)
        completed = [run for run in runs if run.deterministic_metrics is not None]
        metrics = [run.deterministic_metrics for run in completed]
        average = lambda field: round(sum(getattr(x, field) for x in metrics) /
                                      len(metrics), 4) if metrics else 0.0
        run_ids = [run.id for run in runs if run.id is not None]
        manual_good, manual_reviewed = await self.repository.manual_counts(run_ids)
        return LLMQualityAggregateReport(
            dataset_version=dataset_version, configuration=configuration,
            cases=len(runs), completed=len(completed),
            valid=sum(x.passed for x in metrics),
            grounding_pass_rate=average("grounding_pass"),
            coverage_average=average("coverage_score"),
            repetition_average=average("repetition_score"),
            specificity_average=average("specificity_score"),
            conciseness_average=average("conciseness_score"),
            language_pass_rate=average("language_pass"),
            format_pass_rate=average("format_pass"),
            average_quality=average("quality_score"),
            repetition_failures=sum("repetition" in x.failed_checks for x in metrics),
            language_failures=sum(not x.language_pass for x in metrics),
            manual_good=manual_good, manual_reviewed=manual_reviewed,
        )

    @staticmethod
    def compare(left, right):
        fields = (
            "grounding_pass_rate", "coverage_average", "repetition_average",
            "specificity_average", "conciseness_average", "language_pass_rate",
            "format_pass_rate", "average_quality",
        )
        return LLMQualityComparison(
            left=left, right=right,
            deltas={field: round(getattr(right, field) - getattr(left, field), 4)
                    for field in fields},
        )
