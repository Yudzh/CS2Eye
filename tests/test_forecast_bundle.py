from datetime import date
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from cs2eye.api.routers import analysis


async def test_forecast_reuses_matchup_for_prediction(monkeypatch):
    matchup={"team_a":{"score":60},"features":"same-object"}
    calls=[]
    class Service:
        def __init__(self,session):pass
        async def calculate(self,*args):
            calls.append(args)
            return matchup
    async def predict(session,**kwargs):
        assert kwargs['precomputed_matchup'] is matchup
        assert kwargs['series_id']==332
        return {'team_a':{'probability':.6}}
    monkeypatch.setattr(analysis,'MatchupService',Service)
    monkeypatch.setattr(analysis,'predict_win_probability',predict)
    result=await analysis.forecast_bundle(3,6,'bo5','pre_veto',332,AsyncMock())
    assert len(calls)==1
    assert calls[0]==(3,6,'bo5','pre_veto',date.today(),332)
    assert result['matchup'] is matchup
    assert result['probability']['team_a']['probability']==.6


async def test_forecast_rejects_invalid_input_before_calculation():
    with pytest.raises(HTTPException):
        await analysis.forecast_bundle(3,3,session=object())
    with pytest.raises(HTTPException):
        await analysis.forecast_bundle(3,6,format='unknown',session=object())


async def test_forecast_archives_the_displayed_prediction(monkeypatch):
    from types import SimpleNamespace
    from cs2eye.services.prediction_history_service import PredictionHistoryService
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(status='scheduled', winner_team_id=None,
        team_a_id=3, team_b_id=6, format='bo5')
    matchup = {'team_a': {'score': 60}}
    probability = {'prediction_status': 'available', 'team_a': {'probability': .6}}
    calculate = AsyncMock(return_value=matchup)
    predict = AsyncMock(return_value=probability)
    capture = AsyncMock()
    monkeypatch.setattr(analysis.MatchupService, 'calculate', calculate)
    monkeypatch.setattr(analysis, 'predict_win_probability', predict)
    monkeypatch.setattr(PredictionHistoryService, 'capture', capture)
    result = await analysis.forecast_bundle(3, 6, 'bo5', 'pre_veto', 332, session)
    capture.assert_awaited_once_with(332, precomputed_matchup=matchup, precomputed_ml=probability)
    session.commit.assert_awaited_once()
    assert result['probability'] is probability
