from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from tests.test_prediction_results import results_db, replay
from cs2eye.models.team import AnalystFactor, Team
from cs2eye.services.analyst_probability_service import analyst_probability_adjustment
from cs2eye.services.prediction_results_service import PredictionResultsService


async def test_explicit_bonus_reverses_pick_symmetrically_and_keeps_archive(results_db):
    async with results_db() as s:
        (await s.get(Team, 1)).name = "Vitality"
        factor = AnalystFactor(team_id=1,match_id=1,probability_bonus_pp=15,
                               factor_type='positive',text='Manual scenario')
        s.add_all([factor,replay(team_a_probability=Decimal('.4'),team_b_probability=Decimal('.6'))])
        await s.commit()
        forward,details=await analyst_probability_adjustment(s,1,2,.4,series_id=1)
        reverse,_=await analyst_probability_adjustment(s,2,1,.6,series_id=1)
        assert abs(forward-.55)<1e-10
        assert abs(forward+reverse-1)<1e-10
        assert details['base_team_a_probability']==.4
        assert abs(details['impact_team_a_pp']-15)<1e-10
        # A newly added override must not enter a past point-in-time calculation.
        past,details=await analyst_probability_adjustment(s,1,2,.4,series_id=1,as_of=date(2026,10,3))
        assert past==.4 and details is None
        items=(await PredictionResultsService(s).results())['items']
        assert len(items)==1
        assert items[0]['source']=='retrospective'
        assert items[0]['predicted_winner']=='Vitality' and items[0]['correct'] is True
        assert items[0]['archived_correct'] is False
        factor.is_active=False
        await s.flush()
        assert len((await PredictionResultsService(s).results())['items'])==1


async def test_match_scope_expiry_environment_and_unavailable(results_db):
    async with results_db() as s:
        factor=AnalystFactor(team_id=1,match_id=1,probability_bonus_pp=15,
                             factor_type='positive',text='Manual')
        s.add(factor);await s.commit()
        assert await analyst_probability_adjustment(s,1,2,None,series_id=1)==(None,None)
        assert await analyst_probability_adjustment(s,1,2,.4)==(.4,None)
        factor.valid_until=datetime.now(UTC)-timedelta(days=1)
        await s.flush()
        assert await analyst_probability_adjustment(s,1,2,.4,series_id=1)==(.4,None)
        factor.valid_until=None;factor.environment='lan'
        await s.flush()
        assert await analyst_probability_adjustment(s,1,2,.4,series_id=1)==(.4,None)
        factor.environment='any'
        await s.flush()
        p,_=await analyst_probability_adjustment(s,1,2,.95,series_id=1)
        assert p==.99
        factor.factor_type='negative';await s.flush()
        p,_=await analyst_probability_adjustment(s,1,2,.4,series_id=1)
        assert p==.25
