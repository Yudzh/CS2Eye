from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from cs2eye.api.routers.analysis import get_ollama_match_analysis_client
from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.core.config import Settings, settings
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.prompts.match_analysis_v2 import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_input,
)
from cs2eye.prompts.match_analysis_v1 import PROMPT_VERSION as PROMPT_VERSION_V1
from cs2eye.services.match_analysis_context_builder import MatchAnalysisContextBuilder
from cs2eye.services.match_llm_analysis_service import (
    MatchLLMAnalysisService,
    MatchLLMServiceError,
)
from cs2eye.services.match_llm_analysis_validator import MatchLLMAnalysisValidator
from cs2eye.services.ollama_match_analysis_client import (
    MatchAnalysisInvalidResponseError,
    MatchAnalysisProviderError,
    MatchAnalysisProviderResult,
    MatchAnalysisProviderTimeoutError,
    OllamaMatchAnalysisClient,
)
from tests.test_match_analysis_context import full_context_payload, nullable_context_payload
from tests.test_match_llm_analysis import valid_analysis_payload


class FakeBuilder:
    def __init__(self, context: MatchAnalysisContext) -> None:
        self.context = context
        self.calls = []

    async def build(self, *args, **kwargs) -> MatchAnalysisContext:
        self.calls.append((args, kwargs))
        return self.context


class FakeProvider:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    async def generate(
        self, context, *, language, repair_errors=(), previous_analysis=None,
    ):
        self.calls.append({
            "context": context,
            "language": language,
            "repair_errors": repair_errors,
            "previous_analysis": previous_analysis,
        })
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class SpyValidator(MatchLLMAnalysisValidator):
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, context, analysis) -> None:
        self.calls += 1
        super().validate(context, analysis)


def context(payload: dict | None = None) -> MatchAnalysisContext:
    return MatchAnalysisContext.model_validate(payload or full_context_payload())


def analysis(payload: dict | None = None) -> MatchLLMAnalysis:
    return MatchLLMAnalysis.model_validate(payload or valid_analysis_payload())


def result(payload: dict | None = None, *, response_id="resp_1"):
    return MatchAnalysisProviderResult(
        analysis=analysis(payload), response_id=response_id,
        input_tokens=100, output_tokens=40,
    )


def service(builder, provider, *, enabled=True, validator=None, model="test-model"):
    return MatchLLMAnalysisService(
        builder, provider, enabled=enabled, model=model, validator=validator,
    )


async def test_context_is_built_and_passed_to_provider() -> None:
    source = context()
    builder = FakeBuilder(source)
    provider = FakeProvider(result())
    response = await service(builder, provider).analyze(
        1, 2, as_of=datetime(2026, 8, 26, tzinfo=UTC), match_id=123,
    )
    assert builder.calls[0][0] == (1, 2)
    assert provider.calls[0]["context"] is source
    assert response.context is source


async def test_structured_analysis_returns_and_validator_runs() -> None:
    spy = SpyValidator()
    response = await service(FakeBuilder(context()), FakeProvider(result()), validator=spy).analyze_context(
        context(), language="ru",
    )
    assert isinstance(response.analysis, MatchLLMAnalysis)
    assert spy.calls == 1
    assert response.runtime.attempts == 1


async def test_invalid_evidence_triggers_one_repair_retry() -> None:
    invalid = valid_analysis_payload()
    invalid["key_advantages"][0]["evidence_refs"] = ["series:999"]
    first_result = result(invalid)
    provider = FakeProvider(first_result, result(response_id="resp_2"))
    response = await service(FakeBuilder(context()), provider).analyze_context(context())
    assert response.runtime.attempts == 2
    assert response.runtime.input_tokens == 200
    assert "unknown evidence refs" in provider.calls[1]["repair_errors"][0]
    assert provider.calls[1]["previous_analysis"] is first_result.analysis


async def test_second_invalid_response_is_controlled_failure() -> None:
    invalid = valid_analysis_payload()
    invalid["conclusion"]["favored_team"] = "team_b"
    provider = FakeProvider(result(invalid), result(invalid))
    with pytest.raises(MatchLLMServiceError) as caught:
        await service(FakeBuilder(context()), provider).analyze_context(context())
    assert caught.value.code == "llm_validation_failed"
    assert len(provider.calls) == 2


async def test_grounding_hallucination_triggers_repair_and_success() -> None:
    invalid = valid_analysis_payload()
    invalid["key_advantages"][0].update({
        "category": "ml_prediction",
        "evidence_refs": ["prediction"],
        "statement": "Spirit has a 64% chance to win.",
    })
    repaired = valid_analysis_payload()
    repaired["key_advantages"][0].update({
        "category": "ml_prediction",
        "evidence_refs": ["prediction"],
        "statement": "Spirit has about 58% according to ML.",
    })
    provider = FakeProvider(result(invalid), result(repaired, response_id="resp_2"))
    response = await service(FakeBuilder(context()), provider).analyze_context(context())
    assert response.runtime.attempts == 2
    assert response.runtime.repair_attempted is True
    assert "probability_hallucination" in response.runtime.grounding_error_codes
    assert '"64%" is not present' in provider.calls[1]["repair_errors"][0]
    assert response.analysis.key_advantages[0].evidence_kind == "ml"


async def test_service_materializes_required_ml_matchup_contradiction() -> None:
    context_payload = full_context_payload()
    context_payload["prediction"]["team_a_probability"] = 0.4
    context_payload["prediction"]["team_b_probability"] = 0.6
    source = context(context_payload)
    payload = valid_analysis_payload()
    payload["conclusion"]["favored_team"] = "team_b"
    payload["contradictions"] = []
    provider = FakeProvider(result(payload))
    response = await service(FakeBuilder(source), provider).analyze_context(
        source, language="ru",
    )
    assert response.runtime.attempts == 1
    assert len(provider.calls) == 1
    conflict = response.analysis.contradictions[0]
    assert conflict.evidence_refs == ["prediction", "matchup"]
    assert "G2" not in conflict.description  # fixture teams are Spirit/Falcons
    assert "Falcons" in conflict.description
    assert "Spirit" in conflict.description


async def test_repeated_grounding_hallucination_drops_only_invalid_item() -> None:
    invalid = valid_analysis_payload()
    invalid["key_advantages"][0].update({
        "category": "map_pool", "evidence_refs": ["veto"],
        "statement": "Spirit is stronger on Nuke.",
    })
    provider = FakeProvider(result(invalid), result(invalid))
    response = await service(FakeBuilder(context()), provider).analyze_context(context())
    assert len(provider.calls) == 2
    assert response.analysis.key_advantages == []
    assert response.analysis.counter_arguments
    assert "unknown_map" in response.runtime.grounding_error_codes
    assert response.runtime.grounding_valid is True


async def test_ml_favorite_cannot_be_reversed_even_after_retry() -> None:
    invalid = valid_analysis_payload()
    invalid["conclusion"]["favored_team"] = "team_b"
    provider = FakeProvider(result(invalid), result(invalid))
    with pytest.raises(MatchLLMServiceError, match="failed CS2Eye validation"):
        await service(FakeBuilder(context()), provider).analyze_context(context())


async def test_insufficient_context_never_calls_provider() -> None:
    source = context(nullable_context_payload())
    provider = FakeProvider()
    response = await service(FakeBuilder(source), provider).analyze_context(source)
    assert provider.calls == []
    assert response.analysis.analysis_status == "insufficient_data"
    assert response.analysis.conclusion.favored_team == "none"
    assert response.runtime.attempts == 0
    assert response.runtime.provider == "none"
    assert response.analysis.data_limitations
    assert all(
        item.severity == "high" for item in response.analysis.data_limitations
    )


async def test_unavailable_ml_with_partial_data_calls_llm_but_has_no_favorite() -> None:
    context_payload = full_context_payload()
    context_payload["prediction"].update({
        "status": "not_available",
        "quality_gate_passed": False,
        "team_a_probability": None,
        "team_b_probability": None,
    })
    context_payload["data_quality"]["overall_status"] = "partial"
    analysis_payload = valid_analysis_payload()
    analysis_payload["analysis_status"] = "limited"
    analysis_payload["conclusion"].update({
        "favored_team": "none", "advantage": "none", "confidence": "low",
    })
    source = context(context_payload)
    provider = FakeProvider(result(analysis_payload))
    response = await service(FakeBuilder(source), provider).analyze_context(source)
    assert len(provider.calls) == 1
    assert response.analysis.conclusion.favored_team == "none"


@pytest.mark.parametrize(("enabled", "provider"), [
    (False, FakeProvider(result())),
    (True, None),
])
async def test_disabled_or_missing_credentials_is_not_configured(enabled, provider) -> None:
    with pytest.raises(MatchLLMServiceError) as caught:
        await service(
            FakeBuilder(context()), provider, enabled=enabled,
        ).analyze_context(context())
    assert caught.value.code == "llm_not_configured"


@pytest.mark.parametrize(("provider_error", "expected_code"), [
    (MatchAnalysisProviderTimeoutError("timeout"), "llm_timeout"),
    (MatchAnalysisProviderError("provider"), "llm_provider_error"),
    (MatchAnalysisInvalidResponseError("parse"), "llm_invalid_response"),
])
async def test_provider_failures_are_mapped(provider_error, expected_code) -> None:
    with pytest.raises(MatchLLMServiceError) as caught:
        await service(
            FakeBuilder(context()), FakeProvider(provider_error),
        ).analyze_context(context())
    assert caught.value.code == expected_code


def test_language_instruction_is_explicit_and_context_is_compact_json() -> None:
    ru = build_user_input(context(), "ru")
    en = build_user_input(context(), "en")
    assert "только на русском" in ru
    assert "only in English" in en
    assert "только на русском" in build_system_prompt("ru")
    assert "only in English" in build_system_prompt("en")
    assert '"schema_version":"match_analysis_context.v1"' in ru


def test_prompt_does_not_require_conflict_for_neutral_matchup() -> None:
    payload = full_context_payload()
    payload["prediction"]["team_a_probability"] = 0.4
    payload["prediction"]["team_b_probability"] = 0.6
    payload["matchup"]["team_a_score"] = 50.1
    payload["matchup"]["team_b_score"] = 49.9
    prompt = build_user_input(MatchAnalysisContext.model_validate(payload), "ru")
    assert "ML and Matchup favor opposite teams" not in prompt


def test_prompt_v2_is_default_and_v1_remains_available() -> None:
    assert PROMPT_VERSION == "match_analysis_prompt.v2"
    assert PROMPT_VERSION_V1 == "match_analysis_prompt.v1"


def test_model_is_configurable() -> None:
    configured = Settings(_env_file=None, match_llm_model="custom-model")
    assert configured.match_llm_model == "custom-model"


def test_ollama_host_and_qwen_model_are_configurable() -> None:
    configured = Settings(
        _env_file=None, ollama_host="http://ollama:11434", match_llm_model="future:model",
    )
    assert configured.ollama_host == "http://ollama:11434"
    assert configured.match_llm_model == "future:model"


async def test_ollama_adapter_uses_async_chat_and_json_schema() -> None:
    captured = {}

    class FakeOllamaClient:
        async def chat(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                message=SimpleNamespace(content=analysis().model_dump_json()),
                prompt_eval_count=12,
                eval_count=8,
            )

    client = OllamaMatchAnalysisClient(
        host="http://test", model="configured-model", timeout_seconds=3,
    )
    await client.close()
    client._client = FakeOllamaClient()
    provider_result = await client.generate(context(), language="en")
    assert captured["model"] == "configured-model"
    assert captured["format"] != MatchLLMAnalysis.model_json_schema()
    claim_schema = captured["format"]["$defs"]["AnalysisClaim"]
    evidence_items = claim_schema["properties"]["evidence_refs"]["items"]
    assert "series:123" in evidence_items["enum"]
    assert "not-a-real-ref" not in evidence_items["enum"]
    assert "pattern" not in claim_schema["properties"]["statement"]
    conclusion = captured["format"]["$defs"]["AnalysisConclusion"]
    assert conclusion["properties"]["favored_team"]["enum"] == ["team_a"]
    assert captured["options"] == {"temperature": 0}
    assert captured["think"] is True
    assert captured["tools"] == []
    assert captured["messages"][0]["role"] == "system"
    assert "only in English" in captured["messages"][0]["content"]
    user_input = captured["messages"][1]["content"]
    assert "only in English" in user_input
    assert "Use evidence_refs only from this allowlist" in user_input
    assert '"series:123"' in user_input
    assert "Evidence refs allowed for each claim/risk category" in user_input
    assert provider_result.analysis.schema_version == "match_llm_analysis.v1"
    assert provider_result.input_tokens == 12
    assert provider_result.output_tokens == 8


async def test_ollama_adapter_rejects_invalid_structured_payload() -> None:
    class FakeOllamaClient:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                message=SimpleNamespace(content="{}"),
                prompt_eval_count=1,
                eval_count=1,
            )

    client = OllamaMatchAnalysisClient(
        host="http://test", model="configured-model", timeout_seconds=3,
    )
    await client.close()
    client._client = FakeOllamaClient()
    with pytest.raises(MatchAnalysisInvalidResponseError):
        await client.generate(context(), language="ru")


def test_ollama_schema_requires_contradiction_for_ml_matchup_conflict() -> None:
    payload = full_context_payload()
    payload["prediction"]["team_a_probability"] = 0.4
    payload["prediction"]["team_b_probability"] = 0.6
    source = context(payload)
    refs, _ = MatchLLMAnalysisValidator.evidence_registry(source)
    schema = OllamaMatchAnalysisClient._grounded_output_schema(source, refs)
    assert schema["$defs"]["AnalysisConclusion"]["properties"]["favored_team"]["enum"] == ["team_b"]
    assert schema["properties"]["contradictions"]["minItems"] == 1
    assert schema["properties"]["contradictions"]["maxItems"] == 1
    refs = schema["$defs"]["AnalysisContradiction"]["properties"]["evidence_refs"]
    assert refs["items"]["enum"] == ["prediction", "matchup"]
    assert refs["minItems"] == refs["maxItems"] == 2
    assert refs["uniqueItems"] is True


def test_ollama_repair_schema_preserves_detailed_analysis() -> None:
    source = context()
    refs, _ = MatchLLMAnalysisValidator.evidence_registry(source)
    schema = OllamaMatchAnalysisClient._grounded_output_schema(
        source, refs, repair=True,
    )
    for collection in (
        "key_advantages", "counter_arguments", "contradictions", "risks",
        "data_limitations",
    ):
        assert schema["properties"][collection].get("maxItems", 1) > 0
    assert "pattern" not in schema["properties"]["summary"]


def test_ollama_schema_disallows_insufficient_status_for_partial_context() -> None:
    source = context()
    refs, _ = MatchLLMAnalysisValidator.evidence_registry(source)
    schema = OllamaMatchAnalysisClient._grounded_output_schema(source, refs)
    assert schema["properties"]["analysis_status"]["enum"] == ["complete", "limited"]


def test_repair_prompt_preserves_valid_explanation_items() -> None:
    prompt = build_user_input(
        context(), "ru", ("unsupported_number at risks[0].statement",),
        previous_analysis=analysis(),
    )
    assert "Preserve every claim" in prompt
    assert "remove only that item" in prompt
    assert "return empty key_advantages" not in prompt


def test_repair_summary_is_localized_and_uses_team_names() -> None:
    payload = full_context_payload()
    payload["prediction"]["team_a_probability"] = 0.4
    payload["prediction"]["team_b_probability"] = 0.6
    source = context(payload)
    candidate = analysis().model_copy(update={
        "conclusion": analysis().conclusion.model_copy(update={"favored_team": "team_b"}),
    })
    repaired = MatchLLMAnalysisService._with_safe_repair_summary(
        source, candidate, "ru",
    )
    assert source.teams.team_a.name in repaired.summary
    assert source.teams.team_b.name in repaired.summary
    assert "team_a" not in repaired.summary and "team_b" not in repaired.summary


def test_match_llm_schema_is_available_for_ollama() -> None:
    schema = MatchLLMAnalysis.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "conclusion" in schema["properties"]


async def test_runtime_contains_model_prompt_version_and_usage() -> None:
    response = await service(
        FakeBuilder(context()), FakeProvider(result()), model="configured-model",
    ).analyze_context(context())
    assert response.runtime.model == "configured-model"
    assert response.runtime.provider == "ollama"
    assert response.runtime.prompt_version == PROMPT_VERSION
    assert response.runtime.provider_response_id == "resp_1"
    assert response.runtime.input_tokens == 100


async def test_debug_endpoint_runs_builder_then_llm(monkeypatch) -> None:
    source = context()
    provider = FakeProvider(result())
    build_calls = []

    async def fake_build(self, *args, **kwargs):
        build_calls.append((args, kwargs))
        return source

    async def override_session():
        yield object()

    monkeypatch.setattr(MatchAnalysisContextBuilder, "build", fake_build)
    monkeypatch.setattr(settings, "match_llm_enabled", True)
    monkeypatch.setattr(settings, "match_llm_model", "endpoint-model")
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_ollama_match_analysis_client] = lambda: provider
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/analysis/llm-match-analysis", json={
            "team_a_id": 1,
            "team_b_id": 2,
            "as_of": "2026-08-26T00:00:00Z",
            "match_id": 123,
            "language": "ru",
        })
    assert response.status_code == 200
    payload = response.json()
    assert build_calls and provider.calls
    assert payload["context"]["schema_version"] == "match_analysis_context.v1"
    assert payload["analysis"]["schema_version"] == "match_llm_analysis.v1"
    assert payload["runtime"]["model"] == "endpoint-model"
    assert payload["runtime"]["provider"] == "ollama"


async def test_debug_endpoint_hides_provider_error_details(monkeypatch) -> None:
    source = context()

    async def fake_build(self, *args, **kwargs):
        return source

    async def override_session():
        yield object()

    monkeypatch.setattr(MatchAnalysisContextBuilder, "build", fake_build)
    monkeypatch.setattr(settings, "match_llm_enabled", True)
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_ollama_match_analysis_client] = lambda: FakeProvider(
        MatchAnalysisProviderError("secret provider details"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/analysis/llm-match-analysis", json={
            "team_a_id": 1, "team_b_id": 2, "as_of": "2026-08-26T00:00:00Z",
        })
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "llm_provider_error"


async def test_debug_endpoint_reports_llm_not_configured(monkeypatch) -> None:
    source = context()

    async def fake_build(self, *args, **kwargs):
        return source

    async def override_session():
        yield object()

    monkeypatch.setattr(MatchAnalysisContextBuilder, "build", fake_build)
    monkeypatch.setattr(settings, "match_llm_enabled", False)
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/analysis/llm-match-analysis", json={
            "team_a_id": 1, "team_b_id": 2, "as_of": "2026-08-26T00:00:00Z",
        })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_not_configured"


async def test_debug_endpoint_insufficient_fallback_needs_no_configuration(
    monkeypatch,
) -> None:
    source = context(nullable_context_payload())

    async def fake_build(self, *args, **kwargs):
        return source

    async def override_session():
        yield object()

    monkeypatch.setattr(MatchAnalysisContextBuilder, "build", fake_build)
    monkeypatch.setattr(settings, "match_llm_enabled", False)
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/analysis/llm-match-analysis", json={
            "team_a_id": 1, "team_b_id": 2, "as_of": "2026-08-26T00:00:00Z",
            "language": "ru",
        })
    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["analysis_status"] == "insufficient_data"
    assert payload["runtime"]["attempts"] == 0
    assert payload["runtime"]["provider"] == "none"
