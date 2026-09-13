from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import httpx
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye import models  # noqa: F401
from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.api.routers.analysis import get_ollama_match_analysis_client
from cs2eye.core.config import settings
from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun
from cs2eye.services.match_llm_analysis_repository import SQLAlchemyMatchLLMAnalysisRepository
from cs2eye.services.match_llm_analysis_run_service import MatchLLMAnalysisRunService
from cs2eye.services.match_llm_analysis_service import MatchLLMAnalysisService, MatchLLMServiceError
from cs2eye.services.ollama_match_analysis_client import (
    MatchAnalysisProviderError, MatchAnalysisProviderResult,
)
from tests.test_match_analysis_context import full_context_payload


class FakeBuilder:
    def __init__(self, context):
        self.context = context
        self.calls = 0

    async def build(self, *args, **kwargs):
        self.calls += 1
        return self.context


class FakeErrorProvider:
    """Mimics the fixed-plan provider failing outright."""

    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    async def generate_fixed_plan(self, plan, **kwargs):
        self.calls += 1
        raise self.error


class FakeV3Provider:
    def __init__(self, *, prompt_version: str | None = None):
        if prompt_version is not None:
            self.prompt_version = prompt_version

    async def generate_fixed_plan(self, plan, **kwargs):
        expected = plan.expected_winner
        return MatchAnalysisProviderResult(
            analysis=MatchLLMAnalysisV3(
                expected_winner_text=(
                    f"По расчётам должна выиграть {expected.team_name} — {expected.win_probability:.0%}."
                    if expected is not None else "Расчёт победителя недоступен."
                ),
                conclusion_text="Предматчевый вывод сформирован по проверенным данным CS2Eye.",
                form_text="Турнирная форма описана только по переданным результатам команд.",
                maps_text="Недостаточно надёжных данных для сравнения карт." if not plan.maps.key_map_edges
                else f"Ключевая карта {plan.maps.key_map_edges[0].map} заранее определена внутренней аналитикой.",
                teamplay_text="Доступные различия в командной игре заранее отобраны внутренней аналитикой.",
                manual_text="Ручных комментариев аналитика по этому матчу нет.",
            ), input_tokens=50, output_tokens=20,
        )


def context(payload=None):
    return MatchAnalysisContext.model_validate(payload or full_context_payload())


@pytest.fixture
async def persistence():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, SQLAlchemyMatchLLMAnalysisRepository(session)
    await engine.dispose()


def run_service(source, provider, repository, *, enabled=True):
    core = MatchLLMAnalysisService(
        FakeBuilder(source), provider, enabled=enabled, model="model-x",
    )
    return MatchLLMAnalysisRunService(core, repository), core.builder


async def test_fixed_plan_persists_and_v3_wording(persistence):
    _, repository = persistence
    source = context()
    service, _ = run_service(source, FakeV3Provider(), repository)
    response = await service.generate(1, 2, as_of=source.as_of, match_id=123, tournament_id=9)
    run = await repository.get_by_id(response.analysis_run_id)
    assert run.status == "completed" and run.llm_called is True
    assert run.context_snapshot == source.model_dump(mode="json")
    assert "host" not in run.context_snapshot and "api_key" not in run.__dict__
    assert run.analysis_schema_version == "match_llm_analysis.v3"
    assert run.prompt_version == "match_analysis_prompt.v5"
    assert run.explanation_plan_schema_version == "match_explanation_plan.v2"
    assert run.explanation_plan_snapshot == response.explanation_plan.model_dump(mode="json")
    assert (run.attempts, run.input_tokens, run.output_tokens) == (1, 50, 20)
    assert run.schema_valid and run.business_valid and run.grounding_valid
    assert response.analysis.schema_version == "match_llm_analysis.v3"
    assert service.detail(run).analysis.schema_version == "match_llm_analysis.v3"
    child = await service.regenerate(
        response.analysis_run_id, reuse_explanation_plan=True,
    )
    child_run = await repository.get_by_id(child.analysis_run_id)
    assert child_run.source_run_id == response.analysis_run_id
    assert child_run.explanation_plan_snapshot == run.explanation_plan_snapshot


async def test_runtime_prompt_version_reflects_provider_not_a_hardcoded_default(persistence):
    """A configured prompt other than the default must not be misreported.

    settings.match_llm_prompt_version is read by OllamaMatchAnalysisClient and
    exposed as its .prompt_version attribute; the service must echo that value
    in runtime metadata rather than assuming the pipeline always runs v5.
    """
    _, repository = persistence
    source = context()
    service, _ = run_service(
        source, FakeV3Provider(prompt_version="match_analysis_prompt.v4"), repository,
    )
    response = await service.generate(1, 2, as_of=source.as_of, match_id=123)
    assert response.runtime.prompt_version == "match_analysis_prompt.v4"
    run = await repository.get_by_id(response.analysis_run_id)
    assert run.prompt_version == "match_analysis_prompt.v4"


async def test_detail_reads_legacy_v1_snapshot(persistence):
    """The v1 LLM analysis pipeline is gone, but old DB rows must still load.

    This directly inserts a completed run row shaped like pre-v2 data (no
    explanation_plan_snapshot, analysis_schema_version="match_llm_analysis.v1")
    and checks MatchLLMAnalysisRunService.detail() still parses it correctly.
    """
    session, _repository = persistence
    source = context()
    legacy_analysis = {
        "schema_version": "match_llm_analysis.v1",
        "context_schema_version": "match_analysis_context.v1",
        "analysis_status": "complete",
        "conclusion": {
            "favored_team": "team_a",
            "advantage": "small",
            "confidence": "medium",
            "reasoning_basis": "ml_prediction",
        },
        "key_advantages": [{
            "claim_id": "advantage:1",
            "side": "team_a",
            "category": "overall_strength",
            "importance": "high",
            "statement": "Team A has the stronger aggregate profile.",
            "evidence_refs": ["prediction"],
        }],
        "counter_arguments": [],
        "contradictions": [],
        "risks": [],
        "data_limitations": [],
        "summary": "Team A remains the small favorite; the evidence is not unanimous.",
    }
    run = MatchLLMAnalysisRun(
        team_a_id=1, team_b_id=2, as_of=source.as_of, analysis_mode="pre_match",
        language="ru", status="completed", llm_called=True,
        context_schema_version=source.schema_version,
        analysis_schema_version="match_llm_analysis.v1",
        prompt_version="match_analysis_prompt.v1",
        provider="ollama", model="legacy-model",
        context_snapshot=source.model_dump(mode="json"),
        analysis_snapshot=legacy_analysis,
        attempts=1, schema_valid=True, business_valid=True, grounding_valid=True,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    detail = MatchLLMAnalysisRunService.detail(run)

    assert isinstance(detail.analysis, MatchLLMAnalysis)
    assert detail.analysis.schema_version == "match_llm_analysis.v1"
    assert detail.analysis.summary == legacy_analysis["summary"]
    assert detail.runtime.prompt_version == "match_analysis_prompt.v1"
    assert MatchLLMAnalysisRunService.history_item(run).favored_team == "team_a"


async def test_provider_failure_is_stored_and_sanitized(persistence):
    _, repository = persistence
    source = context()
    service, _ = run_service(
        source, FakeErrorProvider(MatchAnalysisProviderError("secret-token")), repository,
    )
    with pytest.raises(MatchLLMServiceError) as caught:
        await service.generate(1, 2, as_of=source.as_of, match_id=123)
    failed = await repository.get_by_id(caught.value.analysis_run_id)
    assert failed.status == "failed" and failed.analysis_snapshot is None
    assert failed.error_code == "llm_provider_error"
    assert "secret-token" not in failed.error_message


async def test_detail_uses_stored_snapshot_and_completed_run_is_immutable(persistence):
    session, repository = persistence
    source_payload = full_context_payload()
    source = context(source_payload)
    service, _ = run_service(source, FakeV3Provider(), repository)
    generated = await service.generate(1, 2, as_of=source.as_of, match_id=123)
    source_payload["teams"]["team_a"]["name"] = "Changed later"
    run = await repository.get_by_id(generated.analysis_run_id)
    detail = service.detail(run)
    assert detail.context.teams.team_a.name == "Spirit"
    run.context_snapshot = {**run.context_snapshot, "schema_version": "changed"}
    with pytest.raises(ValueError, match="immutable"):
        await session.commit()
    await session.rollback()


async def test_latest_history_pagination_and_failed_ignored(persistence):
    _, repository = persistence
    source = context()
    service, _ = run_service(source, FakeV3Provider(), repository)
    first = await service.generate(1, 2, as_of=source.as_of, match_id=123)
    failing, _ = run_service(
        source, FakeErrorProvider(MatchAnalysisProviderError()), repository,
    )
    with pytest.raises(MatchLLMServiceError):
        await failing.generate(1, 2, as_of=source.as_of + timedelta(minutes=1), match_id=123)
    latest_service, _ = run_service(source, FakeV3Provider(), repository)
    second = await latest_service.generate(
        1, 2, as_of=source.as_of + timedelta(minutes=2), match_id=123,
    )
    latest = await repository.get_latest(team_a_id=1, team_b_id=2, match_id=123)
    assert latest.id == second.analysis_run_id
    page = await repository.list_history(match_id=123, limit=2, offset=0)
    assert [row.id for row in page] == sorted([row.id for row in page], reverse=True)
    next_page = await repository.list_history(match_id=123, limit=1, offset=2)
    assert next_page[0].id == first.analysis_run_id
    # Pre-existing gap: MatchLLMHistoryItem.analysis_status reads a "status" key
    # that only the retired v1 plan had; v2 plans (the only kind produced now)
    # have no such field, so this is always None. Not introduced by this change.
    assert service.history_item(latest).analysis_status is None


async def test_regenerate_creates_child_and_reuses_exact_snapshot(persistence):
    _, repository = persistence
    source = context()
    provider = FakeV3Provider()
    service, builder = run_service(source, provider, repository)
    old = await service.generate(1, 2, as_of=source.as_of, match_id=123)
    old_run = await repository.get_by_id(old.analysis_run_id)
    original_snapshot = deepcopy(old_run.context_snapshot)
    builder.context = context({**full_context_payload(), "generated_at": "2026-09-01T00:00:00Z"})
    child = await service.regenerate(old.analysis_run_id, reuse_context=True)
    child_run = await repository.get_by_id(child.analysis_run_id)
    assert child_run.id != old_run.id and child_run.source_run_id == old_run.id
    assert child_run.context_snapshot == original_snapshot == old_run.context_snapshot
    assert builder.calls == 1  # initial generation only; regenerate did not rebuild
    assert old_run.analysis_snapshot == old.analysis.model_dump(mode="json")


def test_migration_upgrade_and_downgrade(tmp_path):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    metadata = MetaData()
    for name in ("teams", "matches", "tournaments"):
        Table(name, metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    path = Path(__file__).parents[1] / "alembic/versions/0032_match_llm_analysis_runs.py"
    spec = spec_from_file_location("migration_0032", path)
    migration = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert "match_llm_analysis_runs" in inspect(connection).get_table_names()
        path_33 = Path(__file__).parents[1] / "alembic/versions/0033_llm_validation_error_codes.py"
        spec_33 = spec_from_file_location("migration_0033", path_33)
        migration_33 = module_from_spec(spec_33)
        assert spec_33 and spec_33.loader
        spec_33.loader.exec_module(migration_33)
        migration_33.op = Operations(MigrationContext.configure(connection))
        migration_33.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("match_llm_analysis_runs")}
        assert "validation_error_codes" in columns

        path_34 = Path(__file__).parents[1] / "alembic/versions/0034_llm_grounding_error_codes.py"
        spec_34 = spec_from_file_location("migration_0034", path_34)
        migration_34 = module_from_spec(spec_34)
        assert spec_34 and spec_34.loader
        spec_34.loader.exec_module(migration_34)
        migration_34.op = Operations(MigrationContext.configure(connection))
        migration_34.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("match_llm_analysis_runs")}
        assert "grounding_error_codes" in columns
        path_35 = Path(__file__).parents[1] / "alembic/versions/0035_match_explanation_plan.py"
        spec_35 = spec_from_file_location("migration_0035", path_35)
        migration_35 = module_from_spec(spec_35)
        assert spec_35.loader is not None
        spec_35.loader.exec_module(migration_35)
        migration_35.op = Operations(MigrationContext.configure(connection))
        migration_35.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("match_llm_analysis_runs")}
        assert {"explanation_plan_schema_version", "explanation_plan_snapshot"} <= columns
        migration_35.downgrade()
        migration_34.downgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("match_llm_analysis_runs")}
        assert "grounding_error_codes" not in columns
        migration_33.downgrade()
        migration.downgrade()
        assert "match_llm_analysis_runs" not in inspect(connection).get_table_names()
    engine.dispose()


async def test_generate_detail_history_latest_and_regenerate_api(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source = context()
    build_calls = 0

    async def override_session():
        async with factory() as session:
            yield session

    async def fake_build(self, *args, **kwargs):
        nonlocal build_calls
        build_calls += 1
        return source

    provider = FakeV3Provider()
    monkeypatch.setattr("cs2eye.api.routers.analysis.MatchAnalysisContextBuilder.build", fake_build)
    monkeypatch.setattr(settings, "match_llm_enabled", True)
    monkeypatch.setattr(settings, "match_llm_model", "api-model")
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_ollama_match_analysis_client] = lambda: provider
    request = {
        "team_a_id": 1, "team_b_id": 2, "as_of": source.as_of.isoformat(),
        "match_id": 123, "tournament_id": 9, "language": "ru",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        generated = await client.post(
            "/api/v1/analysis/llm-match-analysis/generate", json=request,
        )
        assert generated.status_code == 200, generated.text
        run_id = generated.json()["analysis_run_id"]
        source = context({**full_context_payload(), "generated_at": "2026-09-02T00:00:00Z"})
        detail = await client.get(f"/api/v1/analysis/llm-match-analysis/{run_id}")
        assert detail.json()["context"]["generated_at"] == "2026-08-27T08:00:00Z"
        assert build_calls == 1
        latest = await client.get(
            "/api/v1/analysis/llm-match-analysis/latest",
            params={"team_a_id": 1, "team_b_id": 2, "match_id": 123},
        )
        assert latest.json()["analysis_run_id"] == run_id
        history = await client.get(
            "/api/v1/analysis/llm-match-analysis/history",
            params={"match_id": 123, "limit": 1, "offset": 0},
        )
        assert history.status_code == 200
        assert history.json()[0]["id"] == run_id
        assert "context" not in history.json()[0]
        regenerated = await client.post(
            f"/api/v1/analysis/llm-match-analysis/{run_id}/regenerate",
            json={"reuse_context": True},
        )
        assert regenerated.status_code == 200, regenerated.text
        assert regenerated.json()["source_run_id"] == run_id
        assert regenerated.json()["analysis_run_id"] != run_id
        assert regenerated.json()["context"] == detail.json()["context"]
        assert build_calls == 1
    await engine.dispose()


async def test_failed_generate_api_returns_persisted_run_id(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source = context()

    async def override_session():
        async with factory() as session:
            yield session

    async def fake_build(self, *args, **kwargs):
        return source

    monkeypatch.setattr("cs2eye.api.routers.analysis.MatchAnalysisContextBuilder.build", fake_build)
    monkeypatch.setattr(settings, "match_llm_enabled", True)
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_ollama_match_analysis_client] = lambda: FakeErrorProvider(
        MatchAnalysisProviderError("private detail"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        failed = await client.post(
            "/api/v1/analysis/llm-match-analysis/generate", json={
                "team_a_id": 1, "team_b_id": 2, "as_of": source.as_of.isoformat(),
            },
        )
        assert failed.status_code == 502
        run_id = failed.json()["detail"]["analysis_run_id"]
        detail = await client.get(f"/api/v1/analysis/llm-match-analysis/{run_id}")
        assert detail.json()["status"] == "failed"
        assert detail.json()["analysis"] is None
        assert detail.json()["error_code"] == "llm_provider_error"
        assert "private detail" not in detail.json()["error_message"]
    await engine.dispose()
