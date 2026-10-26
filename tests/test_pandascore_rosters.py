from datetime import UTC, date, datetime, timedelta
from copy import deepcopy

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, func

from tests.test_tournament_roster_override import roster_db
from cs2eye.core.config import settings
from cs2eye.models.team import Team, Player, TeamRoster, TeamRosterMember
from cs2eye.models.match import Tournament, TournamentRosterCheck, TournamentRosterOverride
from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.services.pandascore_roster_service import PandaScoreRosterService
from cs2eye.services.effective_roster_service import EffectiveRosterService


NAMES = ['apEX','ZywOo','flameZ','ropz','mezii','jL']
def rows(count=5):
    return [dict(id=100+i, name=name, slug=f'ps-{i}', nationality='FR') for i,name in enumerate(NAMES[:count],1)]


def service(session, main=None, tournament=None, status=200):
    def handler(request):
        if status != 200:
            return httpx.Response(status, json={})
        if request.url.path == '/csgo/teams':
            return httpx.Response(200, json=[{'id':999, 'players':main if main is not None else rows()}])
        if request.url.path == '/tournaments/22222':
            return httpx.Response(200, json={'id':22222,'name':'Group Stage','serie':{'year':2026},'videogame':{'slug':'cs-go'}})
        assert request.url.path == '/tournaments/22222/rosters'
        return httpx.Response(200,json={'type':'Team','rosters':[{'id':999,'players':tournament if tournament is not None else rows()}]})
    def factory(quota,reserve):
        return PandaScoreClient(quota,reserve,transport=httpx.MockTransport(handler))
    return PandaScoreRosterService(session,factory)


async def setup(session, monkeypatch):
    monkeypatch.setattr(settings,'pandascore_api_token',SecretStr('test-only'))
    team=await session.get(Team,1);team.pandascore_id=999
    event=await session.get(Tournament,1);event.pandascore_id=22222
    event.start_date=date.today();event.end_date=date.today()+timedelta(days=3)
    await session.commit()


async def test_main_five_reuses_existing_player_ids_and_history(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        player=await s.get(Player,1);player.steam_id='12345';await s.commit()
        svc=service(s)
        result=await svc.refresh_main(1);await s.commit()
        team=await s.get(Team,1)
        assert result['status']=='saved'
        assert team.pandascore_roster_synced_at
        assert (await s.get(Player,1)).steam_id=='12345'
        assert (await s.get(Player,1)).pandascore_id==101
        assert await s.scalar(select(func.count()).select_from(Player))==7
        assert (await s.get(TeamRoster,1)).fingerprint=='base'
        current=team.current_roster_id
        await svc.refresh_main(1);await s.commit()
        assert team.current_roster_id==current
        assert {x for x in (await s.scalars(select(TeamRosterMember.player_id).where(TeamRosterMember.roster_id==current))).all()}=={1,2,3,4,5}


async def test_six_requires_selection_and_never_truncates(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        svc=service(s,main=rows(6))
        value=await svc.refresh_main(1);await s.commit()
        assert value['status']=='needs_review'
        assert (await s.get(Team,1)).current_roster_id==1
        assert (await s.get(Player,1)).pandascore_id is None
        with pytest.raises(ValueError):await svc.apply_main(1,[101]*5)
        with pytest.raises(ValueError):await svc.apply_main(1,[101,102,103,104,99999])
        await svc.apply_main(1,[101,102,103,104,106]);await s.commit()
        effective=await EffectiveRosterService(s).get_effective_roster(1,None)
        assert {p['id'] for p in effective['players']}=={1,2,3,4,6}
        assert not (await s.get(TeamRoster,1)).is_current


async def test_tournament_roster_separate_and_immutable(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        tour=rows()[:4]+[rows(6)[5]]
        svc=service(s,tournament=tour)
        result=await svc.refresh_tournament(1,1);await s.commit()
        capture=await s.scalar(select(TournamentRosterCheck))
        stamp=capture.checked_at
        assert result['status']=='changed'
        assert capture.added_ids==[6] and capture.missing_ids==[5]
        assert (await s.get(Team,1)).current_roster_id==1
        effective=await EffectiveRosterService(s).get_effective_roster(1,1)
        assert effective['roster_source']=='PANDASCORE_TOURNAMENT_ROSTER'
        assert {p['id'] for p in effective['players']}=={1,2,3,4,6}
        assert effective['stand_in_penalty']==0
        assert await s.scalar(select(func.count()).select_from(TournamentRosterOverride))==0
        result=await service(s,status=500).refresh_tournament(1,1)
        assert result['created']==0 and capture.checked_at==stamp
        historical=await EffectiveRosterService(s).get_effective_roster(1,1,known_before=date.today())
        assert {p['id'] for p in historical['players']}=={1,2,3,4,5}


async def test_unavailable_or_incomplete_never_replaces_rosters(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        assert (await service(s,main=rows(4)).refresh_main(1))['status']=='partial'
        await s.commit()
        with pytest.raises(ValueError,match='ровно пять'):
            await service(s,tournament=rows(6)).refresh_tournament(1,1)
        await s.rollback()
        with pytest.raises(PandaScoreError):
            await service(s,status=403).refresh_main(1)
        assert (await s.get(Team,1)).current_roster_id==1
        assert await s.scalar(select(func.count()).select_from(TournamentRosterCheck))==0


async def test_pandascore_only_player_has_real_provider_identity(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        new={'id':8888,'slug':'new-player','name':'New Player','nationality':'TR'}
        await service(s,main=rows()[:4]+[new]).refresh_main(1);await s.commit()
        player=await s.scalar(select(Player).where(Player.pandascore_id==8888))
        assert player.bo3_id is None and player.bo3_slug is None
        assert player.nickname=='New Player'
        assert player.country_code=='TR'


async def test_ambiguous_identity_fails_atomically(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        s.add(Player(bo3_id=9999,bo3_slug='duplicate',nickname='ZywOo'))
        await s.commit()
        with pytest.raises(ValueError,match='Неоднозначная'):
            await service(s).refresh_main(1)
        await s.rollback()
        assert (await s.get(Player,1)).pandascore_id is None
        assert (await s.get(Team,1)).current_roster_id==1


async def test_default_monitor_uses_pandascore(roster_db,monkeypatch):
    from cs2eye.services.tournament_lineup_monitor import TournamentLineupMonitor
    from unittest.mock import AsyncMock
    async with roster_db() as s:
        spy=AsyncMock(return_value={'status':'unchanged'})
        monkeypatch.setattr(PandaScoreRosterService,'refresh_tournament',spy)
        await TournamentLineupMonitor(s).check(1,1)
        spy.assert_awaited_once_with(1,1)


async def test_manual_tournament_override_keeps_priority(roster_db,monkeypatch):
    async with roster_db() as s:
        await setup(s,monkeypatch)
        await EffectiveRosterService(s).create_manual(1,1,5,7)
        await s.commit()
        await service(s,tournament=rows()[:4]+[rows(6)[5]]).refresh_tournament(1,1);await s.commit()
        effective=await EffectiveRosterService(s).get_effective_roster(1,1)
        assert {p['id'] for p in effective['players']}=={1,2,3,4,7}
        assert effective['roster_source']=='MANUAL'
        assert effective['warnings']


async def test_release_checks_saved_identities(roster_db,monkeypatch):
    from cs2eye.deployment.rosters import verify_rosters
    async with roster_db() as s:
        await setup(s,monkeypatch)
        await service(s).refresh_main(1);await s.commit()
        await service(s).refresh_tournament(1,1);await s.commit()
    report=await verify_rosters(roster_db)
    assert report=={'main':1,'tournament':1,'errors':[]}


def test_roster_migration_preserves_existing_rows_and_allows_provider_only_players():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine,text
    spec=importlib.util.spec_from_file_location('roster_migration',Path(__file__).parents[1]/'alembic/versions/0065_pandascore_rosters.py')
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with create_engine('sqlite://').begin() as conn:
        conn.execute(text('CREATE TABLE teams (id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE tournaments (id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE players (id INTEGER PRIMARY KEY, bo3_id INTEGER NOT NULL UNIQUE, bo3_slug VARCHAR(160) NOT NULL)'))
        conn.execute(text("CREATE TABLE team_rosters (id INTEGER PRIMARY KEY, source VARCHAR(24), CONSTRAINT ck_team_rosters_source CHECK (source IN ('team_import','manual','demo','migration','tournament')))"))
        conn.execute(text("INSERT INTO players VALUES (1,101,'old-player')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            conn.execute(text("INSERT INTO players (id,pandascore_id) VALUES (2,202)"))
            conn.execute(text("INSERT INTO team_rosters VALUES (1,'pandascore')"))
            assert conn.execute(text('SELECT bo3_id FROM players WHERE id=1')).scalar_one()==101
            with pytest.raises(RuntimeError,match='PandaScore-only'):
                migration.downgrade()
            conn.execute(text('DELETE FROM players WHERE id=2'))
            migration.downgrade()
            assert conn.execute(text('SELECT bo3_slug FROM players WHERE id=1')).scalar_one()=='old-player'


async def discovery_setup(session,monkeypatch):
    from cs2eye.models.match import Match
    await setup(session,monkeypatch)
    event=await session.get(Tournament,1);event.pandascore_id=None
    session.add(Team(id=2,bo3_id=222,bo3_slug='opponent',name='Opponent',pandascore_id=998))
    from cs2eye.models.match import TournamentTeam
    session.add(TournamentTeam(tournament_id=1,team_id=2))
    session.add(Match(id=10,tournament_id=1,team_a_id=1,team_b_id=2,match_date=date.today(),format='bo3',status='scheduled'))
    await session.commit()


def discovery_service(session, calls, ambiguous=False):
    row={'id':12345,'league':{'name':'Cup'},'serie':{'name':'1','full_name':'1 2026','year':2026},
         'tournament':{'id':22222},'opponents':[{'type':'Team','opponent':{'id':999}}, {'type':'Team','opponent':{'id':998}}]}
    def handler(request):
        calls.append(request.url.path)
        if '/matches/' in request.url.path:
            if request.url.path.endswith('/upcoming'):
                data=[row,{**row,'league':{'name':'Other Cup'},'tournament':{'id':99999}}]
                if ambiguous:data.append({**row,'tournament':{'id':33333}})
                return httpx.Response(200,json=data)
            return httpx.Response(200,json=[])
        if request.url.path=='/tournaments/22222':
            return httpx.Response(200,json={'id':22222,'name':'Group Stage','serie':{'year':2026},'videogame':{'slug':'cs-go'}})
        assert request.url.path=='/tournaments/22222/rosters'
        other=[dict(id=200+i,name=f'Opponent {i}',slug=f'o{i}') for i in range(1,6)]
        return httpx.Response(200,json={'type':'Team','rosters':[{'id':999,'players':rows()},{'id':998,'players':other}]})
    return PandaScoreRosterService(session,lambda quota,reserve:PandaScoreClient(quota,reserve,transport=httpx.MockTransport(handler)))


async def test_discovers_stage_from_match_pair_and_event_without_kickoff(roster_db,monkeypatch):
    async with roster_db() as s:
        await discovery_setup(s,monkeypatch)
        calls=[]
        result=await discovery_service(s,calls).refresh_tournament(1,1,match_id=10)
        await s.commit()
        assert result['created']==1
        assert (await s.get(Tournament,1)).pandascore_id==22222
        assert {path for path in calls if '/matches/' in path}=={'/csgo/matches/upcoming','/csgo/matches/running','/csgo/matches/past'}
        stamp=(await s.scalar(select(TournamentRosterCheck))).checked_at
        before=len(calls)
        await discovery_service(s,calls).refresh_tournament(1,1,match_id=10)
        assert len(calls)==before
        assert (await s.scalar(select(TournamentRosterCheck))).checked_at==stamp


async def test_ambiguous_stages_do_not_save_a_wrong_binding(roster_db,monkeypatch):
    async with roster_db() as s:
        await discovery_setup(s,monkeypatch)
        with pytest.raises(ValueError,match='неоднозначен'):
            await discovery_service(s,[],ambiguous=True).refresh_tournament(1,1,match_id=10)
        assert (await s.get(Tournament,1)).pandascore_id is None
        assert await s.scalar(select(func.count()).select_from(TournamentRosterCheck))==0


async def test_match_endpoint_saves_both_teams_once_for_whole_event(roster_db,monkeypatch):
    import cs2eye.api.routers.pandascore_rosters as routes
    from cs2eye.models.match import Match
    async with roster_db() as s:
        await discovery_setup(s,monkeypatch)
        calls=[]
        monkeypatch.setattr(routes,'PandaScoreRosterService',lambda session:discovery_service(session,calls))
        first=await routes.ensure_match_rosters(10,s)
        assert all(team['status']=='saved' and len(team['players'])==5 for team in first['teams']), first
        assert await s.scalar(select(func.count()).select_from(TournamentRosterCheck))==2
        before=len(calls)
        s.add(Match(id=11,tournament_id=1,team_a_id=1,team_b_id=2,match_date=date.today()+timedelta(days=2),format='bo3',status='scheduled'))
        await s.commit()
        second=await routes.ensure_match_rosters(11,s)
        assert len(calls)==before
        assert all(team['created']==0 for team in second['teams'])
        assert (await s.get(Team,1)).current_roster_id==1
        assert (await s.get(Match,10)).status=='scheduled'
