import json
import os
import shutil
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.core.config import settings
from cs2eye.db.base import Base
from cs2eye.deployment.ai_reports import export_run, import_reports
from cs2eye.models.ai_report_import import AIReportImport
from cs2eye.models.match import Match, Tournament
from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun as Run
from cs2eye.models.team import Team
from cs2eye.services.match_llm_analysis_repository import SQLAlchemyMatchLLMAnalysisRepository
from tests.test_match_analysis_context import full_context_payload
from tests.test_match_llm_analysis_persistence import persistence, context, run_service, FakeV3Provider


async def database(offset=0):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Team(id=offset+1, bo3_id=10, bo3_slug="spirit", name="Spirit"),
                         Team(id=offset+2, bo3_id=20, bo3_slug="falcons", name="Falcons"),
                         Tournament(id=offset+3, name="Test Cup", year=2026)])
        await session.flush()
        session.add(Match(id=offset+123, tournament_id=offset+3, team_a_id=offset+1,
                          team_b_id=offset+2, match_date=date(2026, 8, 28), format="bo3"))
        await session.commit()
    return factory, engine


def completed_run():
    return Run(match_id=123, tournament_id=3, team_a_id=1, team_b_id=2,
        as_of=datetime(2026, 8, 27, tzinfo=UTC), created_at=datetime(2026, 8, 27, 10, tzinfo=UTC),
        completed_at=datetime(2026, 8, 27, 10, 1, tzinfo=UTC), status="completed",
        analysis_mode="pre_match", language="ru", llm_called=True,
        context_schema_version="match_analysis_context.v1", analysis_schema_version="match_llm_analysis.v3",
        prompt_version="match_analysis_prompt.v5", provider="ollama", model="local-model",
        context_snapshot=full_context_payload(), attempts=1,
        schema_valid=True, business_valid=True, grounding_valid=True,
        analysis_snapshot={"schema_version":"match_llm_analysis.v3",
            "conclusion_text":"Исходный отчёт", "form_text":"Форма", "maps_text":"Карты",
            "teamplay_text":"Командная игра", "manual_text":"Комментарий"})


@pytest.fixture
async def release_databases(tmp_path):
    source, source_engine = await database()
    target, target_engine = await database(1000)
    async with source() as session:
        row = completed_run()
        session.add(row)
        await session.commit()
        path = await export_run(session, row, tmp_path)
    yield source, target, tmp_path, path
    await source_engine.dispose()
    await target_engine.dispose()


async def test_release_import_maps_different_ids_and_preserves_original_report(release_databases):
    source, target, directory, path = release_databases
    document = json.loads(path.read_text())
    async with target() as session:
        result = await import_reports(session, directory)
        await session.commit()
        assert result["imported"] == 1
    async with target() as session:
        result = await import_reports(session, directory)
        await session.commit()
        assert result == {"files": 1, "imported": 0, "existing": 1}
        row = await session.scalar(select(Run))
        assert (row.match_id, row.team_a_id, row.team_b_id, row.tournament_id) == (1123, 1001, 1002, 1003)
        assert row.context_snapshot == document["run"]["context_snapshot"]
        assert row.analysis_snapshot == document["run"]["analysis_snapshot"]
        assert row.created_at.replace(tzinfo=UTC) == datetime(2026, 8, 27, 10, tzinfo=UTC)
        assert row.model == "local-model"
        assert await session.scalar(select(func.count(Run.id))) == 1
        repo = SQLAlchemyMatchLLMAnalysisRepository(session)
        assert (await repo.get_latest(team_a_id=1001, team_b_id=1002, match_id=1123)).id == row.id


async def test_tampered_release_fails_before_any_reports_are_imported(release_databases):
    _, target, directory, path = release_databases
    document = json.loads(path.read_text())
    document["run"]["analysis_snapshot"]["conclusion_text"] = "Подмена"
    (directory / ("f"*64 + ".json")).write_text(json.dumps(document))
    async with target() as session:
        with pytest.raises(ValueError, match="filename"):
            await import_reports(session, directory)
        assert await session.scalar(select(func.count(Run.id))) == 0


async def test_missing_match_fails_instead_of_assigning_report_to_local_id(release_databases):
    _, target, directory, _ = release_databases
    async with target() as session:
        match = await session.get(Match, 1123)
        match.team_b_id = 1001
        await session.commit()
    async with target() as session:
        with pytest.raises(ValueError, match="exactly one server match"):
            await import_reports(session, directory)
        assert await session.scalar(select(func.count(AIReportImport.digest))) == 0


async def test_reports_without_match_keep_pair_scope(release_databases):
    source, target, directory, _ = release_databases
    async with source() as session:
        row = completed_run()
        row.match_id = row.tournament_id = None
        session.add(row)
        await session.commit()
        await export_run(session, row, directory)
    async with target() as session:
        await import_reports(session, directory)
        await session.commit()
        rows = (await session.scalars(select(Run))).all()
        assert {row.match_id for row in rows} == {1123, None}


def test_commit_hook_includes_reports_without_adding_other_local_changes(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    root = Path(__file__).resolve().parents[1]
    folder = tmp_path / "src/cs2eye/deployment/ai_report_artifacts"
    folder.mkdir(parents=True)
    (folder / "report.json").write_text("{}")
    (tmp_path / "other.txt").write_text("unrelated")
    hook = tmp_path / "hook"
    shutil.copy(root / ".githooks/pre-commit", hook)
    subprocess.run(["bash", str(hook)], cwd=tmp_path, check=True)
    staged = subprocess.check_output(["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"], text=True)
    assert staged.strip() == "src/cs2eye/deployment/ai_report_artifacts/report.json"


@pytest.mark.parametrize("environment,expected", [("local", 1), ("production", 0)])
async def test_generation_exports_completed_local_report_automatically(persistence, monkeypatch, environment, expected):
    session, repository = persistence
    monkeypatch.setattr(settings, "app_env", environment)
    monkeypatch.setattr(settings, "ai_report_export_enabled", True)
    monkeypatch.setattr(session, "get_bind", lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    export = AsyncMock()
    monkeypatch.setattr("cs2eye.deployment.ai_reports.export_run", export)
    source = context()
    service, _ = run_service(source, FakeV3Provider(), repository)
    await service.generate(1, 2, as_of=source.as_of, match_id=123, tournament_id=9)
    assert export.await_count == expected
    if expected:
        assert export.await_args.args[1].status == "completed"


def test_report_publish_command_commits_only_reports_pushes_and_deploys(tmp_path):
    root = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()

    git("init", "-b", "telegtam-prod")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", str(remote))
    (checkout / "README").write_text("initial")
    git("add", "README")
    git("commit", "-m", "initial")
    (checkout / "deploy").mkdir()
    shutil.copy(root / "deploy/publish.sh", checkout / "deploy/publish.sh")
    reports = checkout / "src/cs2eye/deployment/ai_report_artifacts"
    reports.mkdir(parents=True)
    (reports / "report.json").write_text("{}")
    (checkout / "unrelated.txt").write_text("keep staged")
    git("add", "unrelated.txt")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$TEST_SSH_LOG"\n')
    ssh.chmod(0o755)
    log = tmp_path / "ssh.log"
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", TEST_SSH_LOG=str(log))
    subprocess.run(["bash", str(checkout / "deploy/publish.sh")], env=env, check=True, capture_output=True)
    assert git("diff", "--cached", "--name-only") == "unrelated.txt"
    assert "report.json" in git("ls-tree", "-r", "--name-only", "HEAD")
    assert log.read_text() == "cs2eye\ncs2eye-deploy\n"
    assert git("rev-parse", "HEAD") == git("rev-parse", "origin/telegtam-prod")


async def test_pandascore_only_team_identity_is_stable_across_release(release_databases):
    from cs2eye.deployment.ai_reports import team_identity, resolve_team
    local, server, directory, path = release_databases
    # Identity lookup must never select arbitrary rows with bo3_id IS NULL.
    async with local() as session:
        team = await session.get(Team, 1)
        team.bo3_id = None
        team.bo3_slug = None
        team.pandascore_id = 131505
        identity = team_identity(team)
        assert identity['pandascore_id'] == 131505
        assert await resolve_team(session, identity) is team
