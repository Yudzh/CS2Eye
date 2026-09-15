from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.analytics.win_probability_config import WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3, WIN_PROBABILITY_FEATURES, WIN_PROBABILITY_FEATURES_V3, WIN_PROBABILITY_FEATURES_V3_CANDIDATES
from cs2eye.db.base import Base
from cs2eye.models.prediction import WinProbabilityModelArtifact
from cs2eye.models.team import Team
from cs2eye.services import win_probability_service as service


@pytest.fixture
async def model_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def metrics(passed: bool) -> dict:
    score = .20 if passed else .30
    return {"metrics": {"test": {"brier_score": score, "log_loss": score}},
            "baselines": {"neutral_50": {"brier_score": .25, "log_loss": .25}}}


def artifact(version: str, *, passed: bool, active: bool = False, forced: bool = False):
    return WinProbabilityModelArtifact(model_version=version, feature_schema_version="features_v1",
        trained_at=datetime.now(UTC), training_series=30, validation_series=10, test_series=10,
        artifact={"features": WIN_PROBABILITY_FEATURES}, metrics=metrics(passed), dataset_report={},
        trained=True, quality_gate_passed=passed, active=active, forced_active=forced)


async def test_failed_gate_requires_force_and_deactivates_previous(model_db) -> None:
    async with model_db() as session:
        previous = artifact("v1", passed=True, active=True)
        candidate = artifact("v2", passed=False)
        session.add_all([previous, candidate]); await session.commit()
        with pytest.raises(ValueError, match="activation rejected"):
            await service.activate_win_probability(session, candidate.id, force=False)
        assert previous.active and not candidate.active
        result = await service.activate_win_probability(session, candidate.id, force=True)
        await session.commit()
        assert result["model_status"] == "experimental"
        assert result["quality_gate_passed"] is False
        assert candidate.active and candidate.forced_active and not previous.active
        assert await session.scalar(select(func.count()).select_from(WinProbabilityModelArtifact).where(WinProbabilityModelArtifact.active.is_(True))) == 1


async def test_passed_gate_activates_without_forced_status(model_db) -> None:
    async with model_db() as session:
        row = artifact("v1", passed=True); session.add(row); await session.commit()
        result = await service.activate_win_probability(session, row.id)
        assert result["model_status"] == "active" and row.active and not row.forced_active


async def test_forced_model_is_used_and_reported_as_experimental(model_db, monkeypatch) -> None:
    async with model_db() as session:
        row = artifact("v1", passed=False, active=True, forced=True)
        session.add_all([row, Team(id=1, bo3_id=1, bo3_slug="a", name="A"), Team(id=2, bo3_id=2, bo3_slug="b", name="B")]); await session.commit()
        async def matchup(*_args, **_kwargs):
            return {"team_a":{"id":1,"name":"A","score":55},"team_b":{"id":2,"name":"B","score":45},"raw_score":55,"reliability":.8,"factors":[],"limitations":[]}
        monkeypatch.setattr(service.MatchupService, "calculate", matchup)
        monkeypatch.setattr(service.WinProbabilityModel, "predict_symmetric", lambda self, rows: [.62])
        result = await service.predict_win_probability(session, 1, 2)
        assert result["prediction_status"] == "available"
        assert result["model_status"] == "experimental" and result["quality_gate_passed"] is False
        assert result["team_a"]["probability"] == .62


async def test_retrain_creates_fresh_inactive_version_and_preserves_old(model_db, monkeypatch) -> None:
    rows = [SimpleNamespace(series_id=i, match_date=date(2026, 1, 1)+timedelta(days=i),
        features={key: (i % 5) / 10 for key in WIN_PROBABILITY_FEATURES}, target=i % 2) for i in range(40)]
    async def dataset(_self, _mode): return rows, {"eligible_series": len(rows)}
    monkeypatch.setattr(service.AnalyticsAsOfService, "build_dataset_v3", dataset)
    original_train = service.WinProbabilityModel.train.__func__
    initial_weights=[]
    def fresh_train(cls, features, targets, **kwargs):
        model=original_train(cls, features, targets, **kwargs)
        initial_weights.append(tuple(model.artifact["coefficients"]))
        return model
    monkeypatch.setattr(service.WinProbabilityModel, "train", classmethod(fresh_train))
    async with model_db() as session:
        old=artifact("v1", passed=False, active=True, forced=True);session.add(old);await session.commit()
        old_metrics=dict(old.metrics);old_artifact=dict(old.artifact)
        first=await service.train_win_probability(session);await session.commit()
        second=await service.train_win_probability(session);await session.commit()
        await session.refresh(old)
        assert first["model_version"] == "v2" and second["model_version"] == "v3"
        assert first["active"] is False and second["active"] is False
        assert old.active and old.forced_active and old.metrics == old_metrics and old.artifact == old_artifact
        assert len(initial_weights) == 6  # candidate + two baselines for each independent retrain


async def test_train_uses_v3_dataset_and_schema_when_requested(model_db, monkeypatch) -> None:
    # Locks in the schema -> dataset-builder -> feature-list wiring without a real,
    # multi-minute build_dataset_v3 run against Postgres (see scripts/train_v3_candidate_model.py
    # for that real-data check). Both the default (matchup_features_v2) and matchup_features_v3
    # schemas now build training rows from build_dataset_v3 -- only the trained feature_names
    # subset differs between them. Rows carry every WIN_PROBABILITY_FEATURES key so both
    # branches can pull from the same fixture.
    rows = [SimpleNamespace(series_id=i, match_date=date(2026, 1, 1)+timedelta(days=i),
        features={key: (i % 5) / 10 for key in WIN_PROBABILITY_FEATURES}, target=i % 2) for i in range(40)]
    calls: list[str] = []
    async def v3_dataset(_self, _mode): calls.append("v3"); return rows, {"eligible_series": len(rows)}
    monkeypatch.setattr(service.AnalyticsAsOfService, "build_dataset_v3", v3_dataset)
    async with model_db() as session:
        default = await service.train_win_probability(session)
        v3 = await service.train_win_probability(session, feature_schema_version=WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3)
        await session.commit()
        assert calls == ["v3", "v3"]
        assert default["metrics"]["test"] is not None  # trained without error, default schema untouched
        row = await session.get(WinProbabilityModelArtifact, v3["artifact_id"])
        assert row.feature_schema_version == WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3
        assert row.artifact["features"] == WIN_PROBABILITY_FEATURES_V3
        # WIN_PROBABILITY_FEATURES_V3 is a forward-selection starting set (grows over time as
        # candidates earn their place) -- assert against the live constant, not a frozen literal.
        assert set(row.artifact["features"]) == set(WIN_PROBABILITY_FEATURES_V3)
        dropped = {"current_roster_advantage", "leadership_advantage", "raw_matchup_centered",
                   "format_bo1_strength", "format_bo3_strength", "format_bo5_strength", *WIN_PROBABILITY_FEATURES_V3_CANDIDATES}
        assert dropped.isdisjoint(row.artifact["features"])
        assert set(row.metrics["coefficients"]) == set(WIN_PROBABILITY_FEATURES_V3)
