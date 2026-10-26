"""Free-list API fixtures, conservative matching, immutable forecasts and audit."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.core.config import settings
from cs2eye.db.base import Base
from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.models.match import Match, MatchResultAudit, ResultSyncQuota, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.models.team import Team
from cs2eye.services.match_result_sync_service import MatchResultSyncService
from cs2eye.services.prediction_history_service import PredictionHistoryService
from cs2eye.services.prediction_results_service import PredictionResultsService


@pytest.fixture
async def db(monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, 'pandascore_api_token', SecretStr('fixture-secret'))
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Team(id=1, name='G2', bo3_id=777, bo3_slug='g2'),
                         Team(id=2, name='NAVI', bo3_id=888, bo3_slug='navi'),
                         Tournament(id=1, name='PGL Masters Bucharest 2026', year=2026),
                         Match(id=1, tournament_id=1, team_a_id=1, team_b_id=2,
                               starts_at=datetime(2026,10,24,16,tzinfo=UTC), match_date=date(2026,10,24),
                               format='bo3', status='scheduled')])
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def row():
    return {'id':1752691,'begin_at':'2026-10-24T16:22:51Z','status':'finished',
            'winner_id':3216,'winner':{'id':3216},'number_of_games':3,'forfeit':False,
            'results':[{'team_id':3210,'score':0},{'team_id':3216,'score':2}],
            'opponents':[{'type':'Team','opponent':{'id':3210,'name':'G2'}},
                         {'type':'Team','opponent':{'id':3216,'name':'Natus Vincere','acronym':'NAVI'}}],
            'league':{'name':'PGL Masters'},'serie':{'name':'Bucharest','full_name':'Bucharest 2026','year':2026},
            'tournament':{'id':22222,'name':'Group Stage'}}


def service(session, rows=None, status=200, headers=None, handler=None):
    def respond(request):
        assert request.url.path == '/csgo/matches/past'
        assert request.headers['Authorization'] == 'Bearer fixture-secret'
        assert 'token=' not in str(request.url)
        return httpx.Response(status, json=rows, headers=headers or {})
    transport = httpx.MockTransport(handler or respond)
    return MatchResultSyncService(session, lambda quota,reserve:PandaScoreClient(quota,reserve,transport=transport))


async def snapshot(session, **changes):
    values = dict(match_id=1,tournament_id=1,source='pre_match',
                  as_of=datetime(2026,10,24,12,tzinfo=UTC),created_at=datetime(2026,10,24,12,tzinfo=UTC),
                  team_a_id=1,team_b_id=2,team_strength_a=60,team_strength_b=40,
                  team_strength_winner_id=1,matchup_a=60,matchup_b=40,matchup_winner_id=1,
                  ml_a_probability=Decimal('.7'),ml_b_probability=Decimal('.3'),ml_winner_id=1,ml_model_version='saved-v1')
    value = PredictionHistorySnapshot(**(values|changes))
    session.add(value)
    await session.commit()
    return value


@pytest.mark.parametrize('reverse',[False,True])
async def test_matching_score_and_forecast_immutability(db,row,reverse):
    match = await db.get(Match,1)
    if reverse:
        match.team_a_id,match.team_b_id = 2,1
    saved = await snapshot(db)
    original = {c.name:getattr(saved,c.name) for c in saved.__table__.columns if c.name != 'actual_winner_id'}
    sync = service(db,[row])
    await sync.run(1)
    assert match.status == 'completed'
    assert match.winner_team_id == 2
    assert (match.team_a_maps_won,match.team_b_maps_won) == ((2,0) if reverse else (0,2))
    assert match.result_source == 'pandascore'
    assert match.result_external_id == 1752691 and match.result_external_id != 777
    assert saved.actual_winner_id == 2
    assert {c.name:getattr(saved,c.name) for c in saved.__table__.columns if c.name != 'actual_winner_id'} == original
    assert (await PredictionResultsService(db).results())['items'][0]['correct'] is False
    count = await db.scalar(select(func.count()).select_from(MatchResultAudit))
    await sync.run(1)
    assert await db.scalar(select(func.count()).select_from(MatchResultAudit)) == count
    # A confirmed identity survives rescheduling, no time/name search is repeated.
    match.starts_at += timedelta(days=2)
    await db.commit()
    await sync.run(1)
    assert match.result_check_status == 'confirmed'


async def test_no_forecast_does_not_create_one(db,row):
    await service(db,[row]).run(1)
    assert (await db.get(Match,1)).status == 'completed'
    assert await db.scalar(select(func.count()).select_from(PredictionHistorySnapshot)) == 0


async def test_ambiguous_and_wrong_tournament_do_not_link(db,row):
    other = deepcopy(row);other['id']=123
    await service(db,[row,other]).run(1)
    match = await db.get(Match,1)
    assert match.result_check_status == 'needs_review' and match.result_external_id is None
    other['serie']['year']=2025
    await service(db,[other]).run(1)
    assert match.result_check_status == 'not_found'
    assert match.winner_team_id is None


@pytest.mark.parametrize('change',[
    {'forfeit':True}, {'status':'canceled'}, {'draw':True}, {'winner_id':999},
    {'winner':{'id':3210}}, {'number_of_games':5},
    {'results':[{'team_id':3210,'score':2},{'team_id':3216,'score':2}]},
    {'results':[]},
])
async def test_bad_results_require_review(db,row,change):
    row.update(change)
    await service(db,[row]).run(1)
    match = await db.get(Match,1)
    assert match.result_check_status == 'needs_review'
    assert match.winner_team_id is None and match.status == 'scheduled'
    assert match.result_proposal == row


async def test_pending_and_missing_match(db,row):
    row['status']='running'
    await service(db,[row]).run(1)
    match = await db.get(Match,1)
    assert match.result_check_status == 'pending'
    assert match.winner_team_id is None
    await service(db,[]).run(1)
    assert match.result_check_status == 'not_found'


async def test_participants_rechecked_on_link(db,row):
    sync = service(db,[row])
    await sync.bind(1, row['id'],3210,3216,'owner','Verified identities')
    row['opponents'][0]['opponent']['id'] = 999
    await sync.run(1)
    match = await db.get(Match,1)
    assert match.result_check_status == 'needs_review'
    assert match.winner_team_id is None


async def test_confirmed_changes_and_manual_override_preserved(db,row):
    sync = service(db,[row])
    await sync.run(1)
    row['results']=[{'team_id':3210,'score':2},{'team_id':3216,'score':1}]
    row['winner_id']=3210;row['winner']={'id':3210}
    await sync.run(1)
    match=await db.get(Match,1)
    assert match.result_check_status == 'needs_review' and match.winner_team_id == 2
    count=await db.scalar(select(func.count()).select_from(MatchResultAudit))
    await sync.run(1)
    assert await db.scalar(select(func.count()).select_from(MatchResultAudit)) == count
    await sync.correct(1,0,2,2,'owner','Reviewed original result')
    await sync.run(1)
    assert match.winner_team_id == 2 and match.result_manual
    assert match.result_source == 'manual'
    audit=(await db.scalars(select(MatchResultAudit).where(MatchResultAudit.actor=='owner'))).one()
    assert audit.reason == 'Reviewed original result'


@pytest.mark.parametrize('status',[401,403,429,500,502])
async def test_api_failure_never_grades_or_changes_result(db,row,status):
    saved=await snapshot(db)
    await service(db,[row],status=status).run(1)
    match=await db.get(Match,1)
    assert match.result_check_status=='error'
    assert match.winner_team_id is None and saved.actual_winner_id is None
    assert 'fixture-secret' not in match.result_error
    if status in (401,403,429):
        assert (await db.get(ResultSyncQuota,1)).blocked_until is not None


async def test_network_failure_and_rate_header(db,row):
    def fail(request): raise httpx.ConnectError('unsafe details',request=request)
    await service(db,handler=fail).run(1)
    match=await db.get(Match,1)
    assert match.result_check_status=='error' and 'unsafe' not in match.result_error
    await service(db,[row],headers={'X-Rate-Limit-Remaining':'0'}).run(1)
    assert match.status=='completed'
    await service(db,[row]).run(1)
    assert match.result_check_status=='error' and match.winner_team_id==2


async def test_pagination_and_request_budget(db,row,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request.url.params)
        page=int(request.url.params['page'])
        return httpx.Response(200,json=[row]*100 if page==1 else [])
    sync=service(db,handler=handler)
    await sync.run(1)
    assert len(calls)==2 and calls[1]['page']=='2'
    assert 'range[begin_at]' in calls[0]
    assert (await db.get(Match,1)).result_check_status=='needs_review'
    monkeypatch.setattr(settings,'result_sync_max_requests',1)
    await sync.run(1)
    assert (await db.get(Match,1)).result_check_status=='error'


async def test_late_and_retrospective_predictions_excluded(db,row):
    saved=await snapshot(db,created_at=datetime(2026,10,24,17,tzinfo=UTC))
    await service(db,[row]).run(1)
    assert saved.actual_winner_id==2
    assert (await PredictionResultsService(db).results())['items']==[]
    item=await PredictionHistoryService(db)._item(saved,await db.get(Match,1))
    assert item['evaluation']=={'eligible':False,'reason':'captured_after_start'}
    assert item['ml']['correct'] is None
    saved.source='retrospective'
    item=await PredictionHistoryService(db)._item(saved,await db.get(Match,1))
    assert item['evaluation']['eligible'] is False


async def test_rolling_budget_shared_and_duplicate_id(db,row):
    sync=service(db,[row])
    quota=await sync.quota()
    quota.requests=[datetime.now(UTC).timestamp()]*950
    await db.commit()
    await sync.run(1)
    assert (await db.get(Match,1)).result_check_status=='error'
    quota.requests=[]
    db.add(Match(id=2,match_date=date(2026,10,24),team_a_id=1,team_b_id=2,format='bo3'))
    await db.commit()
    await sync.bind(1,row['id'],3210,3216,'owner','Verified ID')
    with pytest.raises(ValueError,match='уже связан'):
        await sync.bind(2,row['id'],3210,3216,'owner','Verified ID')


async def test_admin_api_flow_and_release_verification(db,row,monkeypatch):
    from contextlib import asynccontextmanager
    from cs2eye.main import create_app
    from cs2eye.db.session import get_db_session
    from cs2eye.deployment.verify_results import verify
    import cs2eye.api.routers.match_results as routes
    monkeypatch.setattr(routes,'MatchResultSyncService',lambda session:service(session,[row]))
    app=create_app()
    async def dependency(): yield db
    app.dependency_overrides[get_db_session]=dependency
    transport=httpx.ASGITransport(app=app)
    await snapshot(db)
    async with httpx.AsyncClient(transport=transport,base_url='http://test') as client:
        response=await client.post('/api/v1/matches/1/result/check')
        assert response.status_code==200
        data=(await client.get('/api/v1/matches/1')).json()
        assert data['winner_team_id']==2 and data['score']=={'team_a':0,'team_b':2}
        assert data['result_sync']['source']=='pandascore'
        response=await client.put('/api/v1/matches/1/result',json={'team_a':2,'team_b':1,'winner_team_id':1,'actor':'owner','reason':'Confirmed correction'})
        assert response.status_code==200
        data=(await client.get('/api/v1/matches/1/result/audit')).json()
        assert data['items'][0]['actor']=='owner'
        assert data['items'][0]['before']['winner_team_id']==2
        assert data['items'][0]['after']['winner_team_id']==1
        response=await client.put('/api/v1/matches/1/result',json={'team_a':2,'team_b':2,'winner_team_id':1,'actor':'owner','reason':'Invalid'})
        assert response.status_code==422
        assert (await db.get(Match,1)).winner_team_id==1
        response=await client.put('/api/v1/matches/1/result/link',json={'external_id':row['id'],'team_a_external_id':3210,'team_b_external_id':3216,'actor':'owner','reason':'Confirmed mapping'})
        assert response.status_code==200
    @asynccontextmanager
    async def factory(): yield db
    report=await verify(factory,base_url='http://test',transport=transport)
    assert report=={'tournaments':1,'saved_forecasts':1,'saved_results':1}
    monkeypatch.setattr(settings,'app_env','production')
    async with httpx.AsyncClient(transport=transport,base_url='http://test') as client:
        body={'team_a':2,'team_b':1,'winner_team_id':1,'actor':'spoofed','reason':'Verified by owner'}
        assert (await client.put('/api/v1/matches/1/result',json=body)).status_code==422
        assert (await client.put('/api/v1/matches/1/result',json=body,headers={'X-CS2Eye-Admin':'authenticated-owner'})).status_code==200
        audit=(await client.get('/api/v1/matches/1/result/audit')).json()['items']
        assert audit[0]['actor']=='authenticated-owner'


async def test_due_batch_includes_old_days_and_avoids_starvation(db,row,monkeypatch):
    monkeypatch.setattr(settings,'result_sync_max_requests',1)
    match=await db.get(Match,1)
    match.result_external_id=1752691
    match.result_link={'1':3210,'2':3216}
    db.add(Match(id=2,tournament_id=1,team_a_id=1,team_b_id=2,
                 starts_at=datetime(2026,10,20,16,tzinfo=UTC),match_date=date(2026,10,20),
                 format='bo3',status='scheduled'))
    await db.commit()
    sync=service(db,[])
    assert (await sync.run())['checked']==1
    # The untouched older check must remain due, rather than being postponed on budget exhaustion.
    untouched=await db.get(Match,1)
    assert untouched.result_checked_at is None
    assert (await sync.run())['checked']==1
    assert untouched.result_checked_at is not None


async def test_manual_score_survives_demo_recalculation(db,row):
    from cs2eye.services.match_service import MatchService
    sync=service(db,[row])
    await sync.correct(1,0,2,2,'owner','Verified score')
    await MatchService(db).recalculate(1)
    match=await db.get(Match,1)
    assert match.status=='completed' and match.winner_team_id==2


async def test_linked_matches_loaded_in_one_batch(db,row):
    second=deepcopy(row);second['id']=42
    second['begin_at']='2026-10-20T16:00:00Z'
    db.add(Match(id=2,tournament_id=1,team_a_id=1,team_b_id=2,match_date=date(2026,10,20),format='bo3',status='scheduled'))
    await db.commit()
    sync=service(db,[row,second])
    await sync.bind(1,row['id'],3210,3216,'owner','Confirmed identities')
    await sync.bind(2,42,3210,3216,'owner','Confirmed identities')
    calls=[]
    def handler(request):
        calls.append(request)
        assert set(request.url.params['filter[id]'].split(','))=={'1752691','42'}
        return httpx.Response(200,json=[row,second])
    await service(db,handler=handler).run()
    assert len(calls)==1
    assert (await db.get(Match,1)).winner_team_id==2
    assert (await db.get(Match,2)).winner_team_id==2


@pytest.mark.parametrize('change',[{'results':[None,None]}, {'opponents':[None,None]}, {'winner':'invalid'}])
async def test_malformed_match_never_overwrites_saved_result(db,row,change):
    sync=service(db,[row])
    await sync.bind(1,row['id'],3210,3216,'owner','Confirmed mapping')
    row.update(change)
    await sync.run(1)
    match=await db.get(Match,1)
    assert match.result_check_status=='needs_review' and match.winner_team_id is None


async def test_migration_preserves_data_and_roundtrips(tmp_path):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text
    spec=importlib.util.spec_from_file_location('pandascore_migration','alembic/versions/0063_pandascore_results.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine(f'sqlite:///{tmp_path}/migration.sqlite')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE matches (id BIGINT PRIMARY KEY, winner_team_id INTEGER, team_a_maps_won INTEGER, team_b_maps_won INTEGER)'))
        conn.execute(text('INSERT INTO matches VALUES (7, 2, 0, 2)'))
        conn.execute(text('CREATE TABLE prediction_history_snapshots (id INTEGER PRIMARY KEY, model_version TEXT, probability REAL, created_at TEXT)'))
        conn.execute(text("INSERT INTO prediction_history_snapshots VALUES (1, 'original', 0.7, '2026-10-23T12:00:00Z')"))
        forecast=conn.execute(text('SELECT * FROM prediction_history_snapshots')).all()
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            assert conn.execute(text('SELECT winner_team_id, team_a_maps_won, team_b_maps_won FROM matches')).one()==(2,0,2)
            assert conn.execute(text('SELECT * FROM prediction_history_snapshots')).all()==forecast
            assert conn.execute(text('SELECT requests FROM result_sync_quota WHERE id=1')).scalar()=='[]'
            module.downgrade()
            module.upgrade()
            assert conn.execute(text('SELECT * FROM prediction_history_snapshots')).all()==forecast
    engine.dispose()


async def test_concurrent_checks_share_lock_and_do_not_duplicate_audit(db,row):
    import asyncio
    factory=async_sessionmaker(db.bind,expire_on_commit=False)
    running=peak=0
    async def handler(request):
        nonlocal running,peak
        running+=1;peak=max(peak,running)
        await asyncio.sleep(.01)
        running-=1
        return httpx.Response(200,json=[row])
    async def run():
        async with factory() as session:
            await service(session,handler=handler).run(1)
    await asyncio.gather(run(),run())
    assert peak==1
    assert await db.scalar(select(func.count()).select_from(MatchResultAudit))==2


async def test_provider_evidence_and_timer_metadata(db,row):
    from cs2eye.services.match_result_sync_service import result_metadata
    sync=service(db,[row])
    await sync.run(1)
    match=await db.get(Match,1)
    metadata=result_metadata(match)
    assert metadata['provider_match']['opponents'][1]['name']=='Natus Vincere'
    assert metadata['provider_match']['tournament']['name']=='Group Stage'
    assert metadata['link']=={'1':3210,'2':3216}
    assert metadata['next_check_at'] is None
    assert 'token' not in metadata['provider_api_url']
    assert 'fixture-secret' not in str(metadata)
    row['status']='running'
    match.status='scheduled';match.winner_team_id=None
    await db.commit()
    await sync.run(1)
    assert result_metadata(match)['next_check_at'] is not None
    # Rebinding cannot display evidence from a different PandaScore match.
    await sync.bind(1,42,3210,3216,'owner','Different match identity')
    assert result_metadata(match)['provider_match'] is None


async def test_pre_match_manual_check_can_bind_free_upcoming_match(db,row):
    kickoff=datetime.now(UTC)+timedelta(days=1)
    match=await db.get(Match,1)
    match.starts_at=kickoff;match.match_date=kickoff.date()
    row['begin_at']=kickoff.isoformat();row['status']='not_started'
    row['serie']['year']=kickoff.year
    tournament=await db.get(Tournament,1);tournament.year=kickoff.year
    await db.commit()
    def handler(request):
        assert request.url.path=='/csgo/matches/upcoming'
        return httpx.Response(200,json=[row])
    await service(db,handler=handler).run(1)
    assert match.result_external_id==row['id']
    assert match.result_check_status=='pending' and match.winner_team_id is None
    assert match.result_link['_pandascore']['status']=='not_started'
