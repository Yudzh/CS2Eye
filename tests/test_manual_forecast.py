from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select

from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.match import Match
from cs2eye.models.prediction import MatchPrediction, PredictionHistorySnapshot
from tests.test_historical_forecast_recovery import model
from tests.test_prediction_results import results_db


@pytest.fixture
async def manual_api(results_db):
    app = create_app()

    async def override():
        async with results_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_completed_match_generates_labelled_replay_once(results_db, model, manual_api):
    for _ in range(2):
        response = await manual_api.post("/api/v1/prediction-history/matches/1/generate")
        assert response.status_code == 200, response.text
        prediction = response.json()["prediction"]
        assert prediction["source"] == "retrospective"
        assert prediction["team_a_probability"] == .7
    async with results_db() as session:
        assert await session.scalar(select(func.count(MatchPrediction.id))) == 1
        assert await session.scalar(select(func.count(PredictionHistorySnapshot.id))) == 0
        from cs2eye.services.match_analysis_context_builder import MatchAnalysisContextBuilder
        # The Telegram card's default contract is unchanged by the web admin action.
        card = await MatchAnalysisContextBuilder(session).build_card(1)
        assert card["prediction"]["status"] == "not_available"
    from cs2eye.services.historical_forecast_recovery import predict_win_probability
    predict_win_probability.assert_awaited_once()
    assert predict_win_probability.await_args.kwargs["historical_only"] is True


async def test_started_today_uses_strict_historical_data(results_db, model, manual_api):
    now = datetime.now(UTC)
    async with results_db() as session:
        match = await session.get(Match, 1)
        match.match_date = now.date()
        match.starts_at = now - timedelta(hours=1)
        match.status = "scheduled"
        match.winner_team_id = None
        await session.commit()
    response = await manual_api.post("/api/v1/prediction-history/matches/1/generate")
    assert response.status_code == 200, response.text
    assert response.json()["prediction"]["source"] == "retrospective"
    from cs2eye.services.historical_forecast_recovery import predict_win_probability
    assert predict_win_probability.await_args.args[5] == now.date()
    assert predict_win_probability.await_args.kwargs["historical_only"] is True


async def test_original_forecast_is_never_replaced(results_db, model, manual_api):
    async with results_db() as session:
        session.add(PredictionHistorySnapshot(match_id=1, tournament_id=1,
            as_of=datetime(2026, 10, 2, tzinfo=UTC), source="pre_match",
            team_a_id=1, team_b_id=2, team_strength_a=60, team_strength_b=40,
            matchup_a=60, matchup_b=40, ml_model_version="original",
            ml_a_probability=.6, ml_b_probability=.4))
        await session.commit()
    response = await manual_api.post("/api/v1/prediction-history/matches/1/generate")
    assert response.status_code == 200
    assert response.json()["prediction"]["source"] == "pre_match"
    assert response.json()["prediction"]["team_a_probability"] == .6
    from cs2eye.services.historical_forecast_recovery import predict_win_probability
    predict_win_probability.assert_not_awaited()


async def test_future_match_saves_original_on_server(results_db, manual_api, monkeypatch):
    now = datetime.now(UTC)
    async with results_db() as session:
        match = await session.get(Match, 1)
        match.match_date = now.date()
        match.starts_at = now + timedelta(hours=1)
        match.status = "scheduled"
        match.winner_team_id = None
        await session.commit()

    async def capture(service, match_id):
        row = PredictionHistorySnapshot(match_id=match_id, as_of=now, source="pre_match",
            team_a_id=1, team_b_id=2, team_strength_a=60, team_strength_b=40,
            matchup_a=60, matchup_b=40, ml_model_version="server-model",
            ml_a_probability=.6, ml_b_probability=.4)
        service.session.add(row)
        return row

    monkeypatch.setattr("cs2eye.services.manual_forecast_service.PredictionHistoryService.capture", capture)
    response = await manual_api.post("/api/v1/prediction-history/matches/1/generate")
    assert response.status_code == 200
    assert response.json()["prediction"]["source"] == "pre_match"
    async with results_db() as session:
        assert await session.scalar(select(func.count(PredictionHistorySnapshot.id))) == 1


async def test_missing_safe_model_returns_actionable_error(results_db, manual_api, monkeypatch):
    monkeypatch.setattr("cs2eye.services.historical_forecast_recovery.active_model", AsyncMock(return_value=None))
    response = await manual_api.post("/api/v1/prediction-history/matches/1/generate")
    assert response.status_code == 422
    assert "истории" in response.json()["detail"]
    async with results_db() as session:
        assert await session.scalar(select(func.count(MatchPrediction.id))) == 0
    assert (await manual_api.post("/api/v1/prediction-history/matches/999/generate")).status_code == 404


async def test_same_day_replay_never_reads_current_team_features(monkeypatch):
    from types import SimpleNamespace
    from cs2eye.services import win_probability_service as service

    artifact = SimpleNamespace(model_version="v12", feature_schema_version="v3",
        trained_at=datetime(2026, 9, 1, tzinfo=UTC), forced_active=False,
        quality_gate_passed=True, artifact={"features": []})
    monkeypatch.setattr(service, "active_model", AsyncMock(return_value=artifact))
    historical = AsyncMock(return_value={"prediction_features": {"safe-feature": .2},
        "team_a": {"score": 60}, "team_b": {"score": 40}, "reliability": 1})
    monkeypatch.setattr("cs2eye.services.analytics_as_of_service.AnalyticsAsOfService.calculate", historical)
    monkeypatch.setattr(service, "WinProbabilityModel", lambda _: SimpleNamespace(predict_symmetric=lambda _: [.7]))
    monkeypatch.setattr(service, "explain_prediction", lambda *args: {})
    monkeypatch.setattr(service, "_feature_vector", lambda *args: pytest.fail("Current team features used"))
    monkeypatch.setattr("cs2eye.services.analyst_probability_service.analyst_probability_adjustment",
                        AsyncMock(return_value=(.7, None)))
    session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("Current teams queried")))
    result = await service.predict_win_probability(session, 1, 2, as_of=datetime.now(UTC).date(),
                                                   series_id=1, historical_only=True)
    assert result["features"] == {"safe-feature": .2}
    assert result["team_a"]["probability"] == .7
    historical.assert_awaited_once()
