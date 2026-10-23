from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cs2eye.models.match import Match
from cs2eye.services import historical_forecast_recovery as recovery
from tests.test_prediction_results import results_db, replay


@pytest.fixture
def model(monkeypatch):
    model = SimpleNamespace(trained_at=datetime(2026, 9, 1, tzinfo=UTC),
        model_version='v12', feature_schema_version='v3',
        metrics={'split': {key: ['2026-08-01'] for key in ('train_dates', 'validation_dates', 'test_dates')}})
    monkeypatch.setattr(recovery, 'active_model', AsyncMock(return_value=model))
    monkeypatch.setattr(recovery, 'predict_win_probability', AsyncMock(return_value={
        'prediction_status': 'available', 'model_version': 'v12',
        'team_a': {'probability': .7}, 'confidence': .8, 'features': {}, 'basis': 'historical'}))
    return model


async def scheduled(session):
    match = await session.get(Match, 1)
    match.status = 'scheduled'
    match.winner_team_id = None
    await session.flush()
    return match


async def test_recovers_missed_match_once_with_historical_cutoff(results_db, model):
    async with results_db() as s:
        match = await scheduled(s)
        row = await recovery.recover_historical_forecast(s, 1)
        assert row.source == 'historical_replay'
        assert row.feature_snapshot['original_values_recovered'] is False
        assert float(row.team_a_probability) == .7
        recovery.predict_win_probability.assert_awaited_once_with(
            s, 1, 2, 'bo3', 'pre_veto', match.match_date, 1, tournament_id=1)
        assert await recovery.recover_historical_forecast(s, 1) is None


@pytest.mark.parametrize('unsafe', ['trained', 'split', 'missing_split'])
async def test_rejects_models_with_future_or_unknown_training_data(results_db, model, unsafe):
    if unsafe == 'trained':
        model.trained_at = datetime(2026, 10, 3, tzinfo=UTC)
    elif unsafe == 'split':
        model.metrics['split']['test_dates'] = ['2026-10-03']
    else:
        model.metrics = {}
    async with results_db() as s:
        await scheduled(s)
        assert await recovery.recover_historical_forecast(s, 1) is None
        recovery.predict_win_probability.assert_not_awaited()


async def test_skips_completed_future_and_existing_forecasts(results_db, model):
    async with results_db() as s:
        assert await recovery.recover_historical_forecast(s, 1) is None
        match = await scheduled(s)
        match.match_date = date(2099, 1, 1)
        await s.flush()
        assert await recovery.recover_historical_forecast(s, 1) is None
        match.match_date = date(2026, 10, 3)
        s.add(replay())
        await s.flush()
        assert await recovery.recover_historical_forecast(s, 1) is None
        recovery.predict_win_probability.assert_not_awaited()
