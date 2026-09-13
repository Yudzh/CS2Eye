import os
from datetime import UTC, datetime

import pytest

from cs2eye.db.session import AsyncSessionLocal
from cs2eye.services.match_analysis_context_builder import MatchAnalysisContextBuilder
from cs2eye.services.match_llm_analysis_service import MatchLLMAnalysisService
from cs2eye.services.ollama_match_analysis_client import OllamaMatchAnalysisClient


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_INTEGRATION") != "1",
    reason="set RUN_OLLAMA_INTEGRATION=1 with Ollama and the project DB running",
)
async def test_real_ollama_aurora_g2_pipeline() -> None:
    model = os.getenv("MATCH_LLM_MODEL", "qwen3:8b")
    client = OllamaMatchAnalysisClient(
        host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        model=model,
        timeout_seconds=float(os.getenv("MATCH_LLM_TIMEOUT_SECONDS", "60")),
        think=os.getenv("MATCH_LLM_THINK", "true").lower() == "true",
    )
    try:
        async with AsyncSessionLocal() as session:
            builder = MatchAnalysisContextBuilder(session)
            context = await builder.build(
                8,
                9,
                as_of=datetime(2026, 8, 26, tzinfo=UTC),
                match_id=160,
            )
            response = await MatchLLMAnalysisService(
                builder,
                client,
                enabled=True,
                model=model,
            ).explain_context(context)
    finally:
        await client.close()

    prediction = context.prediction
    assert prediction.status == "available"
    assert prediction.team_a_probability is not None
    assert prediction.team_b_probability is not None
    expected_favorite = (
        "team_a"
        if prediction.team_a_probability > prediction.team_b_probability
        else "team_b"
    )
    assert response.explanation_plan.conclusion.favored_team == expected_favorite
    matchup = context.matchup
    assert matchup.team_a_score is not None
    assert matchup.team_b_score is not None
