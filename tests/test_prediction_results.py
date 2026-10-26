from datetime import date, datetime, UTC
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from cs2eye.db.base import Base
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import Team
from cs2eye.models.prediction import MatchPrediction, PredictionHistorySnapshot
from cs2eye.services.prediction_results_service import PredictionResultsService


@pytest.fixture
async def results_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add_all([Team(id=1, bo3_id=1, name="Alpha", bo3_slug="alpha"),
                   Team(id=2, bo3_id=2, name="Bravo", bo3_slug="bravo"),
                   Team(id=3, bo3_id=3, name="Charlie", bo3_slug="charlie"),
                   Tournament(id=1, name="Cup", year=2026),
                   Match(id=1, tournament_id=1, match_date=date(2026,10,3),
                         team_a_id=1, team_b_id=2, status="completed", winner_team_id=1,
                         team_a_maps_won=2, team_b_maps_won=1, format="bo3")])
        await s.commit()
    yield factory
    await engine.dispose()


def replay(**changes):
    values = dict(series_id=1, as_of=date(2026,10,3), mode="pre_veto", source="historical_replay",
                  model_version="v12", feature_schema_version="v3", team_a_id=1, team_b_id=2,
                  team_a_probability=Decimal(".8"), team_b_probability=Decimal(".2"),
                  confidence=Decimal(".8"), feature_snapshot={}, prediction_status="available")
    return MatchPrediction(**(values | changes))


async def test_grades_saved_probabilities_separately_from_pre_match(results_db):
    async with results_db() as s:
        s.add(replay(team_a_id=2, team_b_id=1, team_a_probability=Decimal('.8')))
        s.add(PredictionHistorySnapshot(match_id=1, tournament_id=1, source="pre_match",
            created_at=datetime(2026,10,2,tzinfo=UTC), as_of=datetime(2026,10,2,tzinfo=UTC), team_a_id=1, team_b_id=2,
            team_strength_a=60, team_strength_b=40, matchup_a=60, matchup_b=40,
            ml_a_probability=Decimal('.7'), ml_b_probability=Decimal('.3'), ml_model_version="v12"))
        await s.commit()
        result = await PredictionResultsService(s).results()
        assert len(result['items']) == 2
        historical = next(x for x in result['items'] if x['source']=='retrospective')
        assert historical['correct'] is False
        assert historical['predicted_winner']=='Bravo'
        assert historical['score']=={'team_a':1,'team_b':2}
        official = next(x for x in result['items'] if x['source']=='pre_match')
        assert official['correct'] is True
        assert official['probability']==.7


async def test_ties_unavailable_changed_teams_and_pending_matches(results_db):
    async with results_db() as s:
        s.add_all([replay(team_a_probability=Decimal('.5')),
                   replay(model_version='v13', team_b_id=3),
                   replay(model_version='v14', prediction_status='insufficient_data'),
                   replay(model_version='v15', source='live_saved_prediction')])
        await s.commit()
        result = await PredictionResultsService(s).results()
        assert len(result['items'])==1
        assert result['items'][0]['correct'] is None
        assert result['items'][0]['predicted_winner'] is None
        match = await s.get(Match,1)
        match.status='scheduled'
        await s.flush()
        assert (await PredictionResultsService(s).results())['items']==[]


async def test_current_analyst_factors_do_not_change_archived_forecast(results_db):
    from cs2eye.models.team import AnalystFactor
    async with results_db() as s:
        s.add(replay())
        s.add(AnalystFactor(team_id=2, factor_type="positive", text="Current team factor",
                            probability_bonus_pp=40, is_active=True))
        await s.commit()
        item = (await PredictionResultsService(s).results())["items"][0]
        assert item["team_a_probability"] == .8
        assert item["predicted_winner"] == "Alpha"
        assert item["correct"] is True
        assert "manual_adjustment" not in item


async def test_vitality_explicit_bonus_changes_pick_but_preserves_archive(results_db):
    from cs2eye.models.team import AnalystFactor
    async with results_db() as s:
        team = await s.get(Team, 1)
        team.name = "Vitality"
        s.add(replay(team_a_probability=Decimal('.40287045'), team_b_probability=Decimal('.59712955')))
        s.add(AnalystFactor(team_id=1, factor_type="positive", text="Vitality +15",
                            probability_bonus_pp=15, is_active=True))
        await s.commit()
        item = (await PredictionResultsService(s).results())["items"][0]
        assert item["team_a_probability"] == pytest.approx(.55287045)
        assert item["predicted_winner"] == "Vitality"
        assert item["correct"] is True
        assert item["archived_correct"] is False
        assert item["manual_adjustment"]["base_team_a_probability"] == pytest.approx(.40287045)


async def test_feed_unifies_upcoming_and_results_without_duplicate_picks(results_db):
    from cs2eye.services.prediction_feed_service import PredictionFeedService
    async with results_db() as s:
        s.add_all([
            replay(), replay(model_version='v13', team_a_probability=Decimal('.9')),
            PredictionHistorySnapshot(match_id=1, tournament_id=1, source='pre_match',
                created_at=datetime(2026,10,2,tzinfo=UTC), as_of=datetime(2026,10,2,tzinfo=UTC), team_a_id=1, team_b_id=2,
                team_strength_a=60, team_strength_b=40, matchup_a=60, matchup_b=40,
                ml_a_probability=Decimal('.3'), ml_b_probability=Decimal('.7'), ml_model_version='v12'),
            Match(id=2, tournament_id=1, match_date=date(2026,10,15), team_a_id=1,
                  team_b_id=2, status='scheduled', format='bo3'),
        ])
        await s.commit()
        items = (await PredictionFeedService(s).feed())['items']
        assert len(items) == 2
        played = next(x for x in items if x['match_id'] == 1)
        assert played['source'] == 'pre_match'
        assert played['team_a_probability'] == .3
        assert played['predicted_winner'] == 'Bravo'
        assert played['correct'] is False
        pending = next(x for x in items if x['match_id'] == 2)
        assert pending['team_a_probability'] is None
        assert pending['score'] is None and pending['correct'] is None


async def test_feed_preserves_replay_probability_and_handles_reversed_teams(results_db):
    from cs2eye.services.prediction_feed_service import PredictionFeedService
    from cs2eye.models.team import AnalystFactor
    async with results_db() as s:
        team = await s.get(Team, 1)
        team.name = 'Vitality'
        s.add(AnalystFactor(team_id=1, factor_type='positive', text='Current bonus',
                            probability_bonus_pp=15, is_active=True))
        s.add(replay(team_a_id=2, team_b_id=1, team_a_probability=Decimal('.8')))
        await s.commit()
        items = (await PredictionFeedService(s).feed())['items']
        assert len(items) == 1
        assert items[0]['source'] == 'retrospective'
        assert abs(items[0]['team_a_probability'] - .35) < 1e-8
        assert items[0]['manual_adjustment']['base_team_a_probability'] == pytest.approx(.2)
        assert items[0]['archived_correct'] is False
        assert items[0]['predicted_winner'] == 'Bravo'
        assert items[0]['correct'] is False


async def test_feed_vitality_bonus_flips_pick_and_grade(results_db):
    from cs2eye.models.team import AnalystFactor
    from cs2eye.services.prediction_feed_service import PredictionFeedService
    async with results_db() as s:
        (await s.get(Team, 1)).name = 'Vitality'
        s.add(AnalystFactor(team_id=1, factor_type='positive', text='Vitality +15',
                            probability_bonus_pp=15, is_active=True))
        s.add(replay(team_a_probability=Decimal('.41781576'), team_b_probability=Decimal('.58218424')))
        await s.commit()
        item = (await PredictionFeedService(s).feed())['items'][0]
        assert item['team_a_probability'] == pytest.approx(.56781576)
        assert item['predicted_winner'] == 'Vitality'
        assert item['correct'] is True
        assert item['archived_correct'] is False
        assert float((await s.get(MatchPrediction, 1)).team_a_probability) == pytest.approx(.41781576)
