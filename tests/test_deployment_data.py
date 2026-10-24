from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.deployment.bucharest_2026 import PARTICIPANTS, apply
from cs2eye.deployment.prepare import prepare_forecasts
from cs2eye.models.match import Match, Tournament, TournamentTeam
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.models.team import Team


@pytest.fixture
async def deployment_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Team(id=i, bo3_id=1000+i, name=name, bo3_slug=f"team-{i}")
                         for i, name in enumerate(PARTICIPANTS, 1)])
        await session.commit()
    yield factory
    await engine.dispose()


async def test_data_migration_delivers_tournament_and_preserves_live_results(deployment_db):
    async with deployment_db() as session:
        tournament_id = await session.run_sync(apply)
        await session.commit()
    async with deployment_db() as session:
        assert await session.scalar(select(func.count(Match.id))) == 41
        assert await session.scalar(select(func.count(TournamentTeam.id))) == 16
        match = await session.scalar(select(Match).where(Match.team_a_id.is_not(None)))
        match.status = "completed"
        match.winner_team_id = match.team_a_id
        match.team_a_maps_won = 2
        await session.commit()
        changed_id = match.id
    async with deployment_db() as session:
        assert await session.run_sync(apply) == tournament_id
        await session.commit()
        assert await session.scalar(select(func.count(Match.id))) == 41
        changed = await session.get(Match, changed_id)
        assert (changed.status, changed.team_a_maps_won) == ("completed", 2)


async def test_alembic_upgrade_commits_data_in_migration_transaction(deployment_db):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[1] / "alembic/versions/0057_bucharest_deployment_data.py"
    spec = importlib.util.spec_from_file_location("bucharest_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def upgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    async with deployment_db.kw["bind"].begin() as connection:
        await connection.run_sync(upgrade)
    async with deployment_db() as session:
        assert await session.scalar(select(func.count(Tournament.id))) == 1
        assert await session.scalar(select(func.count(Match.id))) == 41


async def test_incomplete_seed_fails_instead_of_marking_data_ready(deployment_db):
    async with deployment_db() as session:
        tournament = Tournament(name="PGL Masters Bucharest 2026", year=2026)
        session.add(tournament)
        await session.flush()
        session.add(Match(tournament_id=tournament.id, match_date=date(2026, 10, 24),
                          round_label="Swiss round 1 · 0-0 · 1"))
        await session.commit()
    async with deployment_db() as session:
        with pytest.raises(ValueError, match="partially populated"):
            await session.run_sync(apply)


async def test_preparation_preserves_original_forecast_and_reports_missing_started_match(deployment_db):
    now = datetime.now(UTC)
    async with deployment_db() as session:
        session.add_all([Match(id=i, match_date=now.date(), starts_at=now-timedelta(hours=1),
                              status="scheduled", team_a_id=1, team_b_id=2, format="bo3")
                         for i in (100, 101)])
        session.add(PredictionHistorySnapshot(
            match_id=100, as_of=now-timedelta(hours=2), source="pre_match",
            team_a_id=1, team_b_id=2, team_strength_a=60, team_strength_b=40,
            matchup_a=60, matchup_b=40, ml_model_version="original",
            ml_a_probability=Decimal("0.6"), ml_b_probability=Decimal("0.4")))
        await session.commit()
    report = await prepare_forecasts(deployment_db, now=now)
    assert report["available"] == [100]
    assert [error["match_id"] for error in report["errors"]] == [101]
    async with deployment_db() as session:
        assert await session.scalar(select(func.count(PredictionHistorySnapshot.id))) == 1
        original = await session.scalar(select(PredictionHistorySnapshot))
        assert original.ml_model_version == "original"
        assert original.ml_a_probability == Decimal("0.6")


async def test_preparation_stores_new_server_forecast_and_rechecks_on_retry(deployment_db, monkeypatch):
    now = datetime.now(UTC)
    async with deployment_db() as session:
        session.add(Match(id=200, match_date=now.date(), starts_at=now+timedelta(hours=1),
                          status="scheduled", team_a_id=1, team_b_id=2, format="bo3"))
        await session.commit()
    calls = []

    async def capture(service, match_id):
        existing = await service.session.scalar(select(PredictionHistorySnapshot).where(
            PredictionHistorySnapshot.match_id == match_id))
        if existing is not None:
            return existing
        calls.append(match_id)
        row = PredictionHistorySnapshot(match_id=match_id, as_of=now, source="pre_match",
            team_a_id=1, team_b_id=2, team_strength_a=60, team_strength_b=40,
            matchup_a=60, matchup_b=40, ml_model_version="server-model",
            ml_a_probability=Decimal("0.6"), ml_b_probability=Decimal("0.4"))
        service.session.add(row)
        return row

    monkeypatch.setattr("cs2eye.deployment.prepare.PredictionHistoryService.capture", capture)
    for _ in range(2):
        report = await prepare_forecasts(deployment_db, now=now)
        assert report["available"] == [200]
        assert report["errors"] == []
    assert calls == [200]
