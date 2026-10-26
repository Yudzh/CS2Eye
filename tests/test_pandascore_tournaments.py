"""Whole-event imports preserve identities, outcomes, and graph edges."""
import httpx
import pytest
from sqlalchemy import select, func
from tests.test_pandascore_results import db
from cs2eye.models.match import Tournament, Match, TournamentTeam
from cs2eye.models.team import Team
from cs2eye.deployment.pandascore_tournaments import apply
from cs2eye.deployment.reset_beijing_2026 import apply as purge
from cs2eye.services.pandascore_tournament_service import PandaScoreTournamentService
from cs2eye.integrations.pandascore.client import PandaScoreClient


def bundle():
    teams = [{'type':'Team','opponent':{'id':10,'name':'G2','slug':'g2'}},
             {'type':'Team','opponent':{'id':20,'name':'NAVI','slug':'navi'}}]
    return {'series':{'id':11136,'name':'Beijing','full_name':'Beijing 2026','year':2026,'league':{'name':'IEM'}},
        'stages':[{'id':22267,'name':'Group A','type':'offline','tier':'s','begin_at':'2026-11-02T07:00:00Z','end_at':'2026-11-04T23:00:00Z','has_bracket':True,
        'matches':[{'id':100,'name':'Upper Bracket Quarterfinal 1: G2 vs NAVI','status':'not_started','scheduled_at':'2026-11-02T07:00:00Z','number_of_games':3,'opponents':teams}], 'brackets':[]}]}


async def test_repeat_import_and_unknown_team(db):
    data = bundle()
    data['stages'][0]['matches'][0]['opponents'][1]['opponent'] = {'id':30,'name':'New Team','slug':'new-team'}
    first = await db.run_sync(lambda s:apply(s,data))
    await db.commit()
    again = await db.run_sync(lambda s:apply(s,data))
    assert first['id'] == again['id']
    assert again['teams'] == 2 and again['matches'] == 1 and again['warnings']
    assert await db.scalar(select(func.count()).select_from(Tournament)) == 2
    team = await db.scalar(select(Team).where(Team.pandascore_id==30))
    assert team.bo3_id is None and team.bo3_slug is None
    assert (await db.get(Team,1)).bo3_id == 777


async def test_bracket_winner_and_loser_edges(db):
    data=bundle();stage=data['stages'][0]
    stage['matches'] += [{'id':i,'name':name,'status':'not_started','scheduled_at':'2026-11-03T07:00:00Z','number_of_games':3,'opponents':[]} for i,name in [(101,'Upper Final'),(102,'Lower Round 1')]]
    stage['brackets']=[{'id':101,'previous_matches':[{'match_id':100,'type':'winner'}]}, {'id':102,'previous_matches':[{'match_id':100,'type':'loser'}]}]
    await db.run_sync(lambda s:apply(s,data))
    m=await db.scalar(select(Match).where(Match.result_external_id==100))
    assert m.next_match_id and m.loser_next_match_id and m.next_match_id!=m.loser_next_match_id
    await db.run_sync(lambda s:apply(s,data))


async def test_results_and_conflict_rollback(db):
    data=bundle();row=data['stages'][0]['matches'][0]
    row.update(status='finished',results=[{'team_id':10,'score':2},{'team_id':20,'score':0}],winner_id=10)
    result=await db.run_sync(lambda s:apply(s,data));await db.commit()
    row.update(results=[{'team_id':10,'score':0},{'team_id':20,'score':2}],winner_id=20)
    with pytest.raises(ValueError,match='сохранённому результату'):
        await db.run_sync(lambda s:apply(s,data))
    await db.rollback()
    m=await db.scalar(select(Match).where(Match.tournament_id==result['id']))
    assert m.status=='completed' and m.team_a_maps_won==2 and m.winner_team_id==1


async def test_event_purge_only_selected_event_and_repeat(db):
    data=bundle();result=await db.run_sync(lambda s:apply(s,data));await db.commit()
    await db.run_sync(purge);await db.commit()
    await db.run_sync(purge)
    assert await db.get(Tournament,1)
    assert await db.scalar(select(func.count()).select_from(Tournament))==1
    assert await db.scalar(select(func.count()).select_from(Match))==1
    assert await db.scalar(select(func.count()).select_from(Team))==2
    assert not await db.scalar(select(TournamentTeam.id).where(TournamentTeam.tournament_id==result['id']))


async def test_name_search_strips_league_and_year(db):
    def respond(request):
        assert request.url.path=='/csgo/series'
        assert request.url.params['search[name]']=='Beijing'
        assert request.url.params['filter[year]']=='2026'
        return httpx.Response(200,json=[{**bundle()['series'],'tournaments':[{'id':22267,'name':'Group A'}]}])
    svc=PandaScoreTournamentService(db,lambda q,r:PandaScoreClient(q,r,transport=httpx.MockTransport(respond)))
    rows=await svc.search('IEM Beijing 2026')
    assert rows[0]['name']=='IEM Beijing 2026'


async def test_import_missing_dependencies_rolls_back(db):
    data=bundle();data['stages'][0]['brackets']=[{'id':100,'previous_matches':[{'match_id':999,'type':'winner'}]}]
    with pytest.raises(ValueError,match='связи сетки'):
        await db.run_sync(lambda s:apply(s,data))
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(Tournament))==1


async def test_purge_removes_reports_import_receipts_and_forecasts(db):
    from tests.test_ai_report_release import completed_run
    from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun
    from cs2eye.models.ai_report_import import AIReportImport
    from cs2eye.models.prediction import MatchPrediction
    from sqlalchemy import text
    await db.execute(text('PRAGMA foreign_keys=ON'))
    data=bundle();result=await db.run_sync(lambda s:apply(s,data))
    match=await db.scalar(select(Match).where(Match.tournament_id==result['id']))
    report=completed_run();report.match_id=match.id;report.tournament_id=result['id']
    db.add(report);await db.flush()
    db.add(AIReportImport(digest='a'*64,source_origin='test',source_run_id=8,report_run_id=report.id))
    from datetime import date
    db.add(MatchPrediction(series_id=match.id,as_of=date(2026,10,26),mode='pre_match',source='test',
        model_version='v1',feature_schema_version='v1',team_a_id=1,team_b_id=2,
        team_a_probability=.6,team_b_probability=.4,confidence=.5,feature_snapshot={},prediction_status='available'))
    await db.commit()
    await db.run_sync(purge);await db.commit()
    assert await db.scalar(select(func.count()).select_from(MatchPrediction))==0
    assert await db.scalar(select(func.count()).select_from(MatchLLMAnalysisRun))==0
    assert await db.scalar(select(func.count()).select_from(AIReportImport))==0


async def test_beijing_reset_migration_is_repeatable(db):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).parents[1]/'alembic/versions/0068_pandascore_events.py'
    spec=importlib.util.spec_from_file_location('events_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    await db.run_sync(lambda s:apply(s,bundle()));await db.commit()
    def upgrade(session):
        with Operations.context(MigrationContext.configure(session.connection())):
            migration.upgrade()
    await db.run_sync(upgrade);await db.commit()
    await db.run_sync(upgrade);await db.commit()
    assert await db.scalar(select(func.count()).select_from(Tournament))==1
    assert (await db.get(Team,1)).bo3_id==777


async def test_bracket_cycle_rejected(db):
    data=bundle();stage=data['stages'][0]
    stage['brackets']=[{'id':100,'previous_matches':[{'match_id':100,'type':'winner'}]}]
    with pytest.raises(ValueError,match='циклическую'):
        await db.run_sync(lambda s:apply(s,data))
    await db.rollback()


async def test_completed_source_populates_next_round_participants(db):
    data=bundle();stage=data['stages'][0]
    stage['matches'][0].update(status='finished',results=[{'team_id':10,'score':2},{'team_id':20,'score':0}],winner_id=10)
    stage['matches'].append({'id':101,'name':'Upper Final','status':'not_started','scheduled_at':'2026-11-03T07:00:00Z','number_of_games':3,'opponents':[]})
    stage['brackets']=[{'id':101,'previous_matches':[{'match_id':100,'type':'winner'}]}]
    await db.run_sync(lambda s:apply(s,data))
    target=await db.scalar(select(Match).where(Match.result_external_id==101))
    assert target.team_a_id==1
    assert target.round_number==2


async def test_service_import_fetches_stages_and_reports_forecast_readiness(db):
    data=bundle()
    def respond(request):
        path=request.url.path
        if path=='/series/11136':
            return httpx.Response(200,json={**data['series'],'videogame':{'id':3},'tournaments':data['stages']})
        if path=='/tournaments/22267/matches':
            return httpx.Response(200,json=data['stages'][0]['matches'])
        if path=='/tournaments/22267/brackets':
            return httpx.Response(200,json=[])
        raise AssertionError(path)
    svc=PandaScoreTournamentService(db,lambda q,r:PandaScoreClient(q,r,transport=httpx.MockTransport(respond)))
    result=await svc.import_event(11136);await db.commit()
    assert result['teams']==2 and result['matches']==1
    assert any('прогноз не подготовлен' in w for w in result['warnings'])
    again=await svc.import_event(11136)
    assert result['id']==again['id']


async def test_provider_stage_failure_does_not_leave_partial_event(db):
    from cs2eye.integrations.pandascore.client import PandaScoreError
    data=bundle()
    def respond(request):
        if request.url.path=='/series/11136':
            return httpx.Response(200,json={**data['series'],'videogame':{'id':3},'tournaments':data['stages']})
        return httpx.Response(503)
    svc=PandaScoreTournamentService(db,lambda q,r:PandaScoreClient(q,r,transport=httpx.MockTransport(respond)))
    with pytest.raises(PandaScoreError):
        await svc.import_event(11136)
    assert await db.scalar(select(func.count()).select_from(Tournament))==1
    assert await db.scalar(select(func.count()).select_from(Match))==1


async def test_known_provider_name_variant_reuses_local_team(db):
    team=await db.get(Team,1);team.name='Falcons';team.bo3_slug='falcons'
    data=bundle();data['stages'][0]['matches'][0]['opponents'][0]['opponent'].update(name='Team Falcons',slug='falcons-esports')
    await db.run_sync(lambda s:apply(s,data))
    assert await db.scalar(select(func.count()).select_from(Team))==2
    assert team.pandascore_id==10


async def test_import_stores_complete_provider_evidence_for_match_page(db):
    await db.run_sync(lambda s:apply(s,bundle()))
    match=await db.scalar(select(Match).where(Match.result_external_id==100))
    evidence=match.result_link['_pandascore']
    assert evidence['opponents'][0]['name']=='G2'
    assert evidence['league']['name']=='IEM'
    assert evidence['scheduled_at']=='2026-11-02T07:00:00Z'
    assert evidence['status']=='not_started'


async def test_group_quarterfinals_remain_separate_from_playoffs(db):
    from copy import deepcopy
    data=bundle()
    second=deepcopy(data['stages'][0]);second.update(id=22268,name='Group B')
    second['matches'][0]['id']=200
    data['stages'].append(second)
    result=await db.run_sync(lambda s:apply(s,data));await db.commit()
    rows=(await db.scalars(select(Match).where(Match.tournament_id==result['id']))).all()
    assert {(m.group_name,m.stage) for m in rows}=={('Group A','group'),('Group B','group')}
    assert all(not m.is_playoff for m in rows)
    # Reimport repairs the previous importer version's classification too.
    for match in rows:match.stage='quarterfinal'
    await db.commit()
    await db.run_sync(lambda s:apply(s,data))
    assert all(m.stage=='group' for m in rows)


async def test_group_stage_migration_preserves_results_and_other_matches(db):
    from cs2eye.deployment.pandascore_group_stages import apply as repair
    data=bundle();result=await db.run_sync(lambda s:apply(s,data))
    match=await db.scalar(select(Match).where(Match.tournament_id==result['id']))
    match.stage='quarterfinal'
    before=(match.id,match.result_external_id,match.team_a_id,match.team_b_id,match.starts_at,match.team_a_maps_won)
    unrelated=await db.get(Match,1);unrelated.stage='quarterfinal'
    await db.commit()
    assert await db.run_sync(repair)==1
    assert await db.run_sync(repair)==0
    assert match.stage=='group' and unrelated.stage=='quarterfinal'
    assert before==(match.id,match.result_external_id,match.team_a_id,match.team_b_id,match.starts_at,match.team_a_maps_won)
