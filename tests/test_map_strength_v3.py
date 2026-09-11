from datetime import UTC, date, datetime
from types import SimpleNamespace
import inspect
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from cs2eye.db.base import Base
from cs2eye.models.demo import DemoMapResult, DemoRound, DemoKill, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import MapPoolEntry, Tournament, TournamentRosterOverride
from cs2eye.models.team import Team, Player, TeamRoster, TeamRosterMember, TeamRankingSnapshot, MapStrengthV3Snapshot
from cs2eye.analytics.map_strength_v3_config import COMPONENT_WEIGHTS, EXECUTION_WEIGHTS, SIDE_WEIGHTS, ROSTER_WEIGHTS, ECONOMY_MIN_SAMPLE
from cs2eye.services.map_strength_v3_service import MapStrengthV3Service, compose, rate_metric, map_delta, map_status, result_summary, sanity_check
from cs2eye.services.opponent_adjusted_results_service import adjusted_map_quality
from cs2eye.services.performance_profile_service import rank_group_v3
from cs2eye.services.team_strength_v3_service import TeamStrengthV3Service


def metric(score, reliability=80): return {"score":score,"reliability":reliability}


def test_exact_45_25_30():
    assert compose(dict(zip(COMPONENT_WEIGHTS,map(metric,[90,60,80]))),COMPONENT_WEIGHTS)["score"] == 79.5
    assert COMPONENT_WEIGHTS == {"results_quality":.45,"side_performance":.25,"map_execution":.30}


def test_exact_execution_weights():
    assert EXECUTION_WEIGHTS == {"trading":.2,"utility":.2,"opening":.15,"entrying":.1,"economy":.15,"postplant":.1,"retake":.1}
    assert compose(dict(zip(EXECUTION_WEIGHTS,map(metric,[90,80,70,60,50,40,30]))),EXECUTION_WEIGHTS)["score"] == 65.


@pytest.mark.parametrize("ct,t,expected",[(90,30,60),(20,80,50),(90,None,90),(None,80,80),(None,None,None)])
def test_sides_equal_weight_and_unavailable(ct,t,expected):
    v=compose({"ct":metric(ct,80 if ct is not None else 0),"t":metric(t,80 if t is not None else 0)},{"ct":.5,"t":.5})
    assert v["score"]==expected
    if (ct is None) != (t is None): assert v["reliability"]==40


def test_reliability_never_changes_score():
    a=compose({k:metric(91,100) for k in COMPONENT_WEIGHTS},COMPONENT_WEIGHTS)
    b=compose({k:metric(91,1) for k in COMPONENT_WEIGHTS},COMPONENT_WEIGHTS)
    assert a["score"]==b["score"]==91 and a["reliability"]>b["reliability"]


def test_missing_metric_renormalizes():
    v=compose({"a":metric(95),"b":metric(None,0)},{"a":.3,"b":.7})
    assert v["score"]==95 and v["metrics"]["a"]["effective_weight"]==1 and v["coverage"]==.3


def test_empty_and_small_sample_no_shrink():
    assert rate_metric(1,1)["score"]==100 and rate_metric(1,1)["reliability"]==2.5
    assert rate_metric(0,0)["score"] is None
    assert result_summary([])["score"] is None


@pytest.mark.parametrize("key",["force_buy","anti_eco","pistol_conversion"])
def test_rare_economy_unavailable(key):
    v=rate_metric(1,1,minimum=ECONOMY_MIN_SAMPLE[key])
    assert v["score"] is None and v["raw_rate"]==100 and v["reliability"]==0


@pytest.mark.parametrize("won,diff",[(True,3),(False,-3)])
def test_historical_opponent_quality(won,diff):
    assert adjusted_map_quality(won=won,round_diff=diff,opponent_rank=5)["score"]>adjusted_map_quality(won=won,round_diff=diff,opponent_rank=50)["score"]


def test_close_loss_strong_beats_crushing_loss_weak():
    assert adjusted_map_quality(won=False,round_diff=-2,opponent_rank=2)["score"]>adjusted_map_quality(won=False,round_diff=-10,opponent_rank=45)["score"]


def test_unknown_rank(): assert adjusted_map_quality(won=True,round_diff=3,opponent_rank=None)["opponent_strength"] is None


@pytest.mark.parametrize("rank,group",[(10,"top_1_10"),(11,"top_11_20"),(20,"top_11_20"),(21,"top_21_30"),(30,"top_21_30"),(31,"others"),(None,"unknown")])
def test_rank_boundaries(rank,group): assert rank_group_v3(rank)==group


@pytest.mark.parametrize("delta,status",[(8,"VERY_STRONG"),(7.99,"STRONG"),(3,"STRONG"),(2.99,"NEUTRAL"),(-2.99,"NEUTRAL"),(-3,"WEAK"),(-7.99,"WEAK"),(-8,"VERY_WEAK")])
def test_status(delta,status): assert map_status(80,delta)==status


def test_delta_no_clipping_and_no_input_dependency():
    assert map_delta(90,82)==8 and map_delta(100,0)==100 and map_delta(None,80) is None
    assert map_status(None,None)=="NOT_ENOUGH_DATA"


def test_roster_weights(): assert ROSTER_WEIGHTS=={5:1.,4:.8,3:.6,2:.2,1:0.,0:0.}


def test_no_forbidden_formula_dependencies():
    assert set(COMPONENT_WEIGHTS)=={"results_quality","side_performance","map_execution"}
    assert not {"firepower","sniping","clutching","player_strength","form","veto","h2h"}&set(EXECUTION_WEIGHTS)
    source=inspect.getsource(MapStrengthV3Service)
    for forbidden in ("TeamFormV3Service", "TeamMapStrengthService", "top_15", "get_h2h", "VetoService"):
        assert forbidden not in source
    assert "opponent_id" not in inspect.signature(MapStrengthV3Service.calculate).parameters


@pytest.fixture
async def map_db(monkeypatch):
    async def baseline(self,*args,**kwargs): return {"score":82.}
    monkeypatch.setattr(TeamStrengthV3Service,"calculate",baseline)
    engine=create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as s:
        s.add_all([Team(id=i,name=f"Team {i}",bo3_id=i,bo3_slug=f"team{i}",current_rank=1) for i in (1,2)])
        s.add_all([Player(id=i,bo3_id=i,bo3_slug=f"p{i}",nickname=f"P{i}") for i in range(1,11)])
        for rid,ids,start in [(1,range(1,6),date(2026,1,1)),(2,[1,2,3,4,6],date(2026,8,2)),(3,range(6,11),date(2026,10,1))]:
            s.add(TeamRoster(id=rid,team_id=1,fingerprint=str(rid),is_current=rid==1,source="manual",resolution_status="complete",active_from=start))
            s.add_all([TeamRosterMember(roster_id=rid,player_id=i,player_name_snapshot=f"P{i}") for i in ids])
        await s.flush();(await s.get(Team,1)).current_roster_id=1
        s.add(MapPoolEntry(version="test",map_name="nuke",is_active=True));s.add(MapPoolEntry(version="test",map_name="mirage",is_active=True));s.add(MapPoolEntry(version="test",map_name="cache",is_active=False))
        for did,day,rid in [(1,date(2026,8,1),1),(2,date(2026,8,2),2),(3,date(2026,9,5),3),(4,date(2026,10,1),3)]:
            s.add(DemoFile(id=did,tournament_name="Cup",tournament_slug="cup",match_date=day,original_filename=f"{did}.dem",storage_path="/tmp/x",file_size_bytes=1,sha256=str(did),match_id=10 if did in (1,2) else 20))
            s.add(DemoMapResult(id=did,demo_file_id=did,map_name="nuke",team_a_id=1,team_b_id=2,team_a_score=13,team_b_score=7,result_source="demo_parser",metadata_status="complete",bomb_data_status="complete",combat_data_status="complete"))
            s.add(DemoTeamRoster(demo_file_id=did,demo_map_result_id=did,team_id=1,roster_id=rid,team_name_snapshot="Team 1",resolution_status="complete"))
        s.add_all([TeamRankingSnapshot(import_run_id=1,points=100,team_id=2,ranking_date=date(2026,7,30),rank=5),TeamRankingSnapshot(import_run_id=1,points=100,team_id=2,ranking_date=date(2026,8,3),rank=50),TeamRankingSnapshot(import_run_id=1,points=100,team_id=2,ranking_date=date(2026,10,2),rank=1)])
        s.add(Tournament(id=1,name="Cup",year=2026,environment="lan",structure_type="swiss",start_date=date(2026,8,1),end_date=date(2026,10,10)))
        await s.commit()
    yield factory
    await engine.dispose()


async def test_historical_rank_asof_and_future_roster(map_db):
    async with map_db() as s:
        (await s.get(Team,1)).current_roster_id=3
        v=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,9,5))
        assert [o["demo_id"] for o in v["observations"]]==[1,2]
        assert all(o["opponent_rank"]==5 for o in v["observations"])
        assert v["roster_context"]["effective_player_ids"]==[1,2,3,4,6]
        assert [o["weight"] for o in v["observations"]]==[.8,1.]
        assert v["delta_vs_team"]==round(v["score"]-82,2)


async def test_exclude_whole_series_and_self(map_db):
    async with map_db() as s:
        for kwargs in ({"exclude_match_id":10},{"exclude_demo_id":1}):
            v=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,9,5),**kwargs)
            assert v["score"] is None and v["status"]=="NOT_ENOUGH_DATA" and v["reliability"]==0


async def test_unplayed_active_and_historical_pool(map_db):
    async with map_db() as s:
        v=await MapStrengthV3Service(s).pool(1,date(2026,9,5))
        assert {x["map"] for x in v["maps"]}=={"nuke","mirage","cache"}
        empty=next(x for x in v["maps"] if x["map"]=="mirage")
        assert empty["score"] is None and empty["delta_vs_team"] is None
        assert all(side["score"] is None for side in empty["sides"].values())


async def test_override_overlap_permanent_unchanged_future_override_excluded(map_db):
    async with map_db() as s:
        s.add(TournamentRosterOverride(tournament_id=1,team_id=1,player_out_id=5,player_in_id=6,status="MANUAL",source_type="MANUAL",valid_from=date(2026,8,1),source_published_at=datetime(2026,7,31,tzinfo=UTC)))
        s.add(TournamentRosterOverride(tournament_id=1,team_id=1,player_out_id=4,player_in_id=7,status="CONFIRMED",source_type="AUTO",valid_from=date(2026,8,1),source_published_at=datetime(2026,10,1,tzinfo=UTC)))
        await s.commit()
        v=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,8,2),tournament_id=1)
        assert v["roster_context"]["effective_player_ids"]==[1,2,3,4,6]
        assert v["observations"][0]["weight"]==.8
        assert (await s.get(Team,1)).current_roster_id==1
        assert set((await s.scalars(select(TeamRosterMember.player_id).where(TeamRosterMember.roster_id==1))).all())=={1,2,3,4,5}


async def test_no_side_data_never_uses_overall(map_db):
    async with map_db() as s:
        v=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,8,2))
        assert v["score"]>50 and v["reliability"]<20
        assert v["sides"]["ct"]["score"] is None and v["sides"]["t"]["score"] is None
        assert v["components"]["results_quality"]["effective_weight"]==1
        assert sanity_check(v)==[]
        v["score"]=float("nan")
        with pytest.raises(ValueError,match="non-finite"): sanity_check(v)


@pytest.mark.parametrize("side",["ct","t"])
def test_raw_sides_opening_conversion_bomb_and_missing_other_side(side):
    service=MapStrengthV3Service(None)
    events=[{"demo_id":1,"weight":1.,"own_a":True,"combat_available":True,"bomb_available":True,"side_stat":None}]
    rounds=[SimpleNamespace(id=i,demo_file_id=1,round_number=i,team_a_side=side.upper(),team_b_side="T" if side=="ct" else "CT",winner_team_id=1 if i==1 else 2,team_a_economy="full_buy",team_b_economy="eco",is_pistol_round=False,bomb_planted=True) for i in (1,2)]
    kills=[SimpleNamespace(demo_file_id=1,round_id=i,is_teamkill=False,is_suicide=False,attacker_team_id=1 if i==1 else 2,victim_team_id=2 if i==1 else 1) for i in (1,2)]
    totals=service._round_metrics(1,events,rounds,kills)
    assert totals[side]["round_winrate"]==[1,2]
    assert totals[side]["conversion"]==[1,1] and totals[side]["recovery"]==[0,1]
    assert totals[side]["retake" if side=="ct" else "postplant"]==[1,2]
    assert totals[side]["postplant" if side=="ct" else "retake"]==[0,0]
    assert totals["t" if side=="ct" else "ct"]["round_winrate"]==[0,0]


async def test_api_contract_and_nulls(map_db):
    from httpx import ASGITransport, AsyncClient
    from fastapi import FastAPI
    from cs2eye.api.routers.analysis import router
    from cs2eye.db.session import get_db_session
    app=FastAPI();app.include_router(router,prefix="/api/v1")
    async def session_override():
        async with map_db() as s: yield s
    app.dependency_overrides[get_db_session]=session_override
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
        response=await client.get("/api/v1/analysis/teams/1/maps-v3/mirage?as_of=2026-09-05")
        assert response.status_code==200,response.text
        value=response.json()["map_strength_v3"]
        assert value["score"] is None and value["status"]=="NOT_ENOUGH_DATA"
        assert set(value["components"])==set(COMPONENT_WEIGHTS)
        pool=await client.get("/api/v1/analysis/teams/1/maps-v3?as_of=2026-09-05")
        assert pool.status_code==200
        assert all(isinstance(item["map_strength_v3"],dict) for item in pool.json()["maps"])


async def test_snapshot_nullable_and_legacy_untouched(map_db):
    async with map_db() as s:
        team=await s.get(Team,1)
        before=team.team_strength_v3
        v=await MapStrengthV3Service(s).calculate(1,"mirage",force=True)
        await s.flush()
        snap=await s.scalar(select(MapStrengthV3Snapshot))
        assert snap.map_score is None and snap.map_delta is None
        assert snap.breakdown["roster_context"]==v["roster_context"]
        assert team.team_strength_v3==before


def test_old_history_cannot_dominate():
    from cs2eye.services.map_strength_v3_service import cap_old_history
    events=cap_old_history([{"overlap":5,"weight":1.}]*3 + [{"overlap":2,"weight":.2}]*30)
    assert sum(e["weight"] for e in events if e["overlap"]==2)==pytest.approx(.75)
    assert sum(e["weight"] for e in events if e["overlap"]==5)==3


async def test_future_opponent_and_veto_do_not_change_strength(map_db):
    from cs2eye.models.match import Match
    async with map_db() as s:
        s.add(Team(id=3,name="Other",bo3_id=3,bo3_slug="other"))
        s.add_all([Match(id=100,team_a_id=1,team_b_id=2,match_date=date(2026,9,5)),
                   Match(id=101,team_a_id=1,team_b_id=3,match_date=date(2026,9,5))])
        await s.flush()
        a=await MapStrengthV3Service(s).calculate(1,"nuke",match_id=100)
        b=await MapStrengthV3Service(s).calculate(1,"nuke",match_id=101)
        assert a["score"]==b["score"] and a["components"]==b["components"]
        (await s.get(DemoFile,1)).map_role="team_pick"
        c=await MapStrengthV3Service(s).calculate(1,"nuke",match_id=100)
        assert c["score"]==a["score"]


async def test_same_day_override_is_not_historically_known(map_db):
    async with map_db() as s:
        s.add(TournamentRosterOverride(tournament_id=1,team_id=1,player_out_id=5,player_in_id=6,status="MANUAL",source_type="MANUAL",valid_from=date(2026,8,1),source_published_at=datetime(2026,8,2,tzinfo=UTC)))
        await s.flush()
        v=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,8,2),tournament_id=1)
        assert v["roster_context"]["effective_player_ids"]==[1,2,3,4,5]
        assert v["observations"][0]["weight"]==1.


async def test_changing_team_baseline_changes_only_delta(map_db,monkeypatch):
    async with map_db() as s:
        a=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,8,2))
        async def baseline(self,*args,**kwargs): return {"score":20.}
        monkeypatch.setattr(TeamStrengthV3Service,"calculate",baseline)
        b=await MapStrengthV3Service(s).calculate(1,"nuke",date(2026,8,2))
        assert a["score"]==b["score"] and a["components"]==b["components"]
        assert b["delta_vs_team"]-a["delta_vs_team"]==pytest.approx(62.)


async def test_profile_weights_raw_observations_and_missing_openings():
    from unittest.mock import AsyncMock
    from cs2eye.services.performance_profile_service import _raw_profile
    def player(trades):
        return SimpleNamespace(demo_file_id=1 if trades else 2,player_id=1,kills=20,deaths=10,total_damage=1500,
            combat_data={"trade_kills":trades,"trade_opportunities":10,"deaths_traded":trades,"deaths_not_traded":10-trades},utility_data={})
    peers={}
    for tid,trades in [(1,0),(2,10)]:
        peers[tid]={scope:_raw_profile(rounds=100,kills=50,deaths=40,damage=5000,awp_kills=0,
            combat={"available":True,"trade_kills":trades,"trade_opportunities":10,"deaths_traded":trades,"deaths_not_traded":10-trades},utility={},scope=scope,maps=2) for scope in ("overall","ct","t")}
    service=MapStrengthV3Service(None);service.profiles._dataset=AsyncMock(return_value={"team":peers})
    totals={side:{"round_winrate":[10,20]} for side in ("ct","t")}
    v=await service._profile(1,"nuke",date(2026,9,5),[{"demo_id":1,"weight":1.,"players":[player(10)]},{"demo_id":2,"weight":.8,"players":[player(0)]}],totals,None,[],[])
    trade=v["overall"]["trading"]
    assert trade["breakdown"][0]["raw_value"]==pytest.approx(10/18)
    assert v["overall"]["opening"]["score"] is None
    assert v["overall"]["entrying"]["score"] is None
    assert v["ct"]["firepower"]["score"] is None
    assert v["t"]["firepower"]["score"] is None


async def test_stale_team_json_is_not_used_as_baseline(map_db):
    async with map_db() as s:
        team=await s.get(Team,1)
        team.team_strength_v3_breakdown={"score":1,"calculation_revision":"obsolete"}
        await s.commit()
        v=await MapStrengthV3Service(s).calculate(1,"nuke")
        assert v["team_strength_v3"]==82.
        assert team.team_strength_v3_breakdown["score"]==1
