from datetime import date, datetime, UTC

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.models.match import Tournament, TournamentRosterOverride, TournamentTeam
from cs2eye.models.team import AnalystFactor, Player, Team, TeamRoster, TeamRosterMember
from cs2eye.services.effective_roster_service import EffectiveRosterService, roster_applicability
from cs2eye.services.tournament_lineup_monitor import LineupResult, TournamentLineupMonitor


@pytest.fixture
async def roster_db():
    engine=create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as s:
        team=Team(id=1,bo3_id=1,bo3_slug="vitality",name="Vitality")
        players=[Player(id=i,bo3_id=i,bo3_slug=f"p{i}",nickname=name,player_strength_v3=50+i) for i,name in enumerate(["apEX","ZywOo","flameZ","ropz","mezii","jL","Y"],1)]
        roster=TeamRoster(id=1,team_id=1,fingerprint="base",is_current=True,source="manual",resolution_status="complete",active_from=date(2026,1,1))
        s.add_all([team,*players,roster]);await s.flush();team.current_roster_id=1
        s.add_all([TeamRosterMember(roster_id=1,player_id=i,player_name_snapshot=players[i-1].nickname) for i in range(1,6)])
        for tid,start,end in ((1,date(2026,9,1),date(2026,9,10)),(2,date(2026,10,1),date(2026,10,10))):
            s.add(Tournament(id=tid,name=f"Cup {tid}",year=2026,environment="lan",structure_type="swiss",start_date=start,end_date=end));s.add(TournamentTeam(tournament_id=tid,team_id=1))
        await s.commit()
    yield factory
    await engine.dispose()


async def test_permanent_and_manual_effective_rosters_are_separate(roster_db):
    async with roster_db() as s:
        service=EffectiveRosterService(s)
        before=await service.get_effective_roster(1,1,as_of=date(2026,9,2))
        assert [x["id"] for x in before["effective_roster"]]==[1,2,3,4,5]
        await service.create_manual(1,1,5,6);await s.commit()
        factor = await s.scalar(select(AnalystFactor).where(AnalystFactor.team_id == 1))
        assert factor is not None
        assert factor.factor_type == "negative" and factor.category == "roster"
        assert "jL играет вместо mezii" in factor.text
        assert factor.valid_until.date() == date(2026, 9, 10)
        value=await service.get_effective_roster(1,1,as_of=date(2026,9,5))
        assert [x["id"] for x in value["effective_roster"]]==[1,2,3,4,6]
        assert value["stand_in_penalty"]==-3 and len(value["analytical_factors"])==1
        members=set((await s.scalars(select(TeamRosterMember.player_id).where(TeamRosterMember.roster_id==1))).all())
        assert members=={1,2,3,4,5}


async def test_priority_dates_scope_multiple_and_disable(roster_db):
    async with roster_db() as s:
        now=datetime(2026,8,20,tzinfo=UTC)
        s.add_all([
            TournamentRosterOverride(tournament_id=1,team_id=1,player_out_id=5,player_in_id=7,status="CONFIRMED",source_type="AUTO",valid_from=date(2026,9,1),valid_until=date(2026,9,10),detected_at=now),
            TournamentRosterOverride(tournament_id=1,team_id=1,player_out_id=4,player_in_id=7,status="DETECTED",source_type="AUTO",valid_from=date(2026,9,1),valid_until=date(2026,9,10),detected_at=now),
        ]);await s.commit()
        manual=await EffectiveRosterService(s).create_manual(1,1,5,6);await s.commit()
        service=EffectiveRosterService(s);active=await service.get_effective_roster(1,1,as_of=date(2026,9,5))
        assert {x["id"] for x in active["effective_roster"]}=={1,2,3,6,7}
        assert active["stand_in_penalty"]==-6 and active["replacements"][0]["status"]=="MANUAL"
        assert (await service.get_effective_roster(1,1,as_of=date(2026,8,31)))["replacements"]==[]
        assert (await service.get_effective_roster(1,1,as_of=date(2026,9,11)))["replacements"]==[]
        assert (await service.get_effective_roster(1,2,as_of=date(2026,10,2)))["replacements"]==[]
        manual.is_active=False;await s.commit()
        fallback=await service.get_effective_roster(1,1,as_of=date(2026,9,5))
        assert any(x["player_in"]["id"]==7 for x in fallback["replacements"])


async def test_auto_never_overwrites_manual(roster_db):
    class Adapter:
        async def get_tournament_lineup(self,*_): return LineupResult("available",[1,2,3,4,7],"confirmed","test")
        async def get_match_lineup(self,*_): return LineupResult("unavailable")
    async with roster_db() as s:
        await EffectiveRosterService(s).create_manual(1,1,5,6);await s.commit()
        result=await TournamentLineupMonitor(s,Adapter()).check(1,1);await s.commit()
        assert result["created"]==0
        effective=await EffectiveRosterService(s).get_effective_roster(1,1,as_of=date(2026,9,5))
        assert effective["effective_roster"][-1]["id"]==6


def test_form_roster_applicability():
    assert roster_applicability({1,2,3,4,5},{1,2,3,4,5})==1.0
    assert roster_applicability({1,2,3,4,6},{1,2,3,4,5})==0.8
    assert roster_applicability({1,2,3,6,7},{1,2,3,4,5})==0.6
