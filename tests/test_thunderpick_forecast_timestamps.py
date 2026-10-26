from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from cs2eye.db.base import Base
from cs2eye.models.team import Team
from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.services.prediction_result_eligibility import eligibility
from cs2eye.deployment.thunderpick_forecast_timestamps import apply, KICKOFFS, NAME, TEAM_BO3_IDS


@pytest.fixture
def data():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        names = list(dict.fromkeys(n for a,b,_ in KICKOFFS for n in (a,b)))
        teams = {n: Team(id=100+i, name=n, bo3_id=TEAM_BO3_IDS[n]) for i,n in enumerate(names)}
        session.add_all(teams.values())
        tournament = Tournament(id=99, name=NAME, year=2026)
        session.add(tournament)
        for i,(a,b,_) in enumerate(KICKOFFS):
            session.add(Match(id=200+i,tournament_id=99,team_a_id=teams[a].id,team_b_id=teams[b].id,
                match_date=date(2026,10,15),status='completed',format='bo3',
                team_a_maps_won=2, team_b_maps_won=0, winner_team_id=teams[a].id))
        session.add(Match(id=300,tournament_id=99,team_a_id=teams['Legacy'].id,team_b_id=teams['PARIVISION'].id,
            match_date=date(2026,10,14), starts_at=datetime(2026,10,14,13,30,tzinfo=UTC),status='completed',format='bo3'))
        session.add(PredictionHistorySnapshot(match_id=300,tournament_id=99,source='pre_match',
            team_a_id=teams['Legacy'].id,team_b_id=teams['PARIVISION'].id,
            created_at=datetime(2026,10,15,4,tzinfo=UTC),as_of=datetime.fromisoformat('2026-10-14T08:13:02.186369+00:00'),
            team_strength_a=60,team_strength_b=40,matchup_a=60,matchup_b=40,
            ml_a_probability=Decimal('0.59798130'),ml_b_probability=Decimal('0.40201870'),ml_model_version='v12',
            matchup_factors={'recovery':{'original_values_recovered':True}}))
        session.commit()
        yield session
    engine.dispose()


def test_repeatable_repair_preserves_picks_and_results(data):
    snapshot = data.scalar(select(PredictionHistorySnapshot))
    original = (snapshot.ml_a_probability,snapshot.ml_b_probability,snapshot.ml_model_version,snapshot.as_of)
    assert apply(data) == {'kickoffs':4,'archived_timestamp':1}
    assert eligibility(snapshot,data.get(Match,300))[0]
    assert original == (snapshot.ml_a_probability,snapshot.ml_b_probability,snapshot.ml_model_version,snapshot.as_of)
    assert data.get(Match,200).winner_team_id is not None
    assert data.get(Match,200).team_a_maps_won == 2
    assert apply(data) == {'kickoffs':0,'archived_timestamp':0}


def test_incomplete_prerequisites_do_not_change_anything(data):
    snapshot = data.scalar(select(PredictionHistorySnapshot))
    snapshot.ml_a_probability = Decimal('.1')
    with pytest.raises(ValueError,match='disagrees'):
        apply(data)
    assert all(data.get(Match,i).starts_at is None for i in range(200,204))


def test_provider_renames_and_duplicate_display_names_use_stable_ids(data):
    for team in data.scalars(select(Team)):
        team.name = {'Aurora':'Aurora Gaming','Falcons':'Team Falcons','BetBoom':'BetBoom Team',
                     'Ninjas in Pyjamas':'NIP'}.get(team.name,team.name)
    data.add(Team(name='Aurora',bo3_id=999999))
    data.commit()
    assert apply(data) == {'kickoffs':4,'archived_timestamp':1}
    assert apply(data) == {'kickoffs':0,'archived_timestamp':0}
