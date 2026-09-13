import argparse
import asyncio
import json

from cs2eye.api.schemas.llm_quality import LLMQualityConfiguration
from cs2eye.core.config import settings
from cs2eye.db.session import AsyncSessionLocal, dispose_engine
from cs2eye.llm_quality.dataset_v2 import DATASET_V2
from cs2eye.services.llm_quality_evaluation_service import LLMQualityEvaluationService
from cs2eye.services.llm_quality_repository import SQLAlchemyLLMQualityRepository
from cs2eye.services.ollama_match_analysis_client import OllamaMatchAnalysisClient


def parser():
    result = argparse.ArgumentParser(prog="python -m cs2eye.llm_quality")
    commands = result.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--dataset", default="llm_quality_dataset.v2")
    evaluate.add_argument("--provider", default="ollama")
    evaluate.add_argument("--model", required=True)
    evaluate.add_argument("--prompt", required=True)
    evaluate.add_argument("--think", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--dataset", default="llm_quality_dataset.v2")
    inspect.add_argument("--provider", default="ollama")
    inspect.add_argument("--model", required=True)
    inspect.add_argument("--prompt", required=True)
    inspect.add_argument("--think", action="store_true")
    return result


async def run(arguments):
    if arguments.dataset != DATASET_V2.schema_version:
        raise SystemExit(f"unknown dataset: {arguments.dataset}")
    if arguments.provider != "ollama":
        raise SystemExit(f"unsupported provider: {arguments.provider}")
    configuration = LLMQualityConfiguration(
        provider=arguments.provider, model=arguments.model,
        prompt_version=arguments.prompt, reasoning={"think": arguments.think,
                                                     "temperature": 0},
    )
    try:
        async with AsyncSessionLocal() as session:
            repository = SQLAlchemyLLMQualityRepository(session)
            service = LLMQualityEvaluationService(
                repository,
                lambda config: OllamaMatchAnalysisClient(
                    host=settings.ollama_host, model=config.model,
                    timeout_seconds=settings.match_llm_timeout_seconds,
                    think=bool(config.reasoning.get("think")),
                    prompt_version=config.prompt_version,
                ),
            )
            if arguments.command == "evaluate":
                runs = await service.evaluate(DATASET_V2, configuration)
                await session.commit()
                report = await service.report(DATASET_V2.schema_version, configuration, runs)
                print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
            else:
                runs = await repository.list_runs(DATASET_V2.schema_version, configuration)
                report = await service.report(DATASET_V2.schema_version, configuration, runs)
                failures = [{
                    "case_id": item.case_id,
                    "failed_checks": (item.deterministic_metrics.failed_checks
                                      if item.deterministic_metrics else [item.error_code]),
                    "output": (item.llm_output_snapshot.model_dump(mode="json")
                               if item.llm_output_snapshot else None),
                } for item in runs if item.status == "failed"]
                print(json.dumps({"report": report.model_dump(mode="json"),
                                  "failures": failures}, ensure_ascii=False, indent=2))
    finally:
        await dispose_engine()


def main():
    arguments = parser().parse_args()
    asyncio.run(run(arguments))


if __name__ == "__main__":
    main()
