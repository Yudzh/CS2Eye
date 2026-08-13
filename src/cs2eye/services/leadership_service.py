from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from statistics import pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.leadership_config import COACH_MODEL_VERSION,COACH_WEIGHTS,IGL_MODEL_VERSION,IGL_WEIGHTS
from cs2eye.analytics.scoring.core import FactorInput,sample_reliability,score_factors
from cs2eye.models.demo import TeamMapAggregate
from cs2eye.models.team import Player,Team,TeamParticipantMembership,TeamRoster
from cs2eye.services.team_map_strength_service import calculate_map_strength,scope_performance
from cs2eye.services.veto_service import VetoService

def clamp(x:float)->float:return max(0,min(100,x))
def num(x:Any)->float|None:return float(x) if x is not None else None
def nested(data:dict|None,*keys:str)->float|None:
    value:Any=data
    for key in keys:
        if not isinstance(value,dict):return None
        value=value.get(key)
    return num(value)
def mean(xs):
    values=[x for x in xs if x is not None]
    return sum(values)/len(values) if values else None
def residual_score(actual:float|None,expected:float|None)->float|None:
    return clamp(50+(actual-expected)*2) if actual is not None and expected is not None else None

def expected_performance(player_strengths:list[float],map_strengths:list[float],opponent_rank_score:float|None=50)->float|None:
    """Coach/IGL-free baseline: roster quality 55%, map quality 30%, opposition 15%."""
    roster=mean(player_strengths);maps=mean(map_strengths)
    parts=[(roster,.55),(maps,.30),(opponent_rank_score,.15)]
    available=[x for x in parts if x[0] is not None]
    return sum(x*w for x,w in available)/sum(w for _,w in available) if available else None

def leadership_score(factors:list[FactorInput],maps:int,model_version:str)->dict:
    coverage=sum(f.available and f.normalized_score is not None for f in factors)/len(factors)
    reliability=sample_reliability(maps,12)*(.65+.35*coverage)
    result=score_factors(factors,reliability)
    return {"score":result.final_score,"raw_score":result.raw_score,"reliability":result.reliability,"confidence_adjustment":result.confidence_adjustment,"model_version":model_version,"sample":{"maps":maps,"available_factors":sum(f.available for f in factors),"total_factors":len(factors)},"factors":[f.__dict__ for f in result.factors]}

def calculate_igl(*,actual:float|None,expected:float|None,maps:int,t_side:float|None,full_buy:float|None,force_vs_full:float|None,anti_eco:float|None,opening_conversion:float|None,opening_recovery:float|None,postplant:float|None,trade:float|None,strong:float|None)->dict:
    residual=None if actual is None or expected is None else actual-expected
    values={"team_overperformance":residual_score(actual,expected),"t_side_quality":mean([t_side,opening_conversion,opening_recovery,postplant,trade]),"full_buy_tactical":mean([full_buy,force_vs_full,anti_eco]),"opening_management":mean([opening_conversion,opening_recovery]),"postplant":postplant,"trading_teamplay":trade,"strong_opponents":strong}
    labels={"team_overperformance":"Team overperformance vs expected","t_side_quality":"T-side management","full_buy_tactical":"Full-buy tactical performance","opening_management":"Opening conversion and recovery","postplant":"Postplant management","trading_teamplay":"Trading/teamplay","strong_opponents":"Strong-opponent performance"}
    factors=[FactorInput(k,labels[k],{"actual":actual,"expected":expected,"residual":residual} if k=="team_overperformance" else v,v,IGL_WEIGHTS[k],maps,sample_reliability(maps,10),"Management attribution signal; correlation, not causal proof",v is not None) for k,v in values.items()]
    result=leadership_score(factors,maps,IGL_MODEL_VERSION);result["management_residual"]=round(residual,2) if residual is not None else None;result["actual_performance"]=actual;result["expected_performance"]=expected
    return result

def calculate_coach(*,actual:float|None,expected:float|None,maps:int,veto_quality:float|None,map_development:float|None,opponent_prep:float|None,player_development:float|None,consistency:float|None,roster_change_penalty:float=1)->dict:
    residual=None if actual is None or expected is None else actual-expected
    values={"team_overperformance":residual_score(actual,expected),"veto_quality":veto_quality,"map_pool_development":map_development,"opponent_preparation":opponent_prep,"roster_player_development":player_development,"consistency":consistency}
    labels={"team_overperformance":"Team overperformance vs expected","veto_quality":"Veto selection quality","map_pool_development":"Map pool development","opponent_preparation":"Opponent-specific preparation","roster_player_development":"Roster/player development","consistency":"Residual consistency"}
    factors=[FactorInput(k,labels[k],v,v,COACH_WEIGHTS[k],maps,sample_reliability(maps,15),"Coach-period correlation; does not establish causation",v is not None) for k,v in values.items()]
    result=leadership_score(factors,maps,COACH_MODEL_VERSION);result["reliability"]=round(result["reliability"]*roster_change_penalty,4);result["score"]=round(50+(result["raw_score"]-50)*result["reliability"],2);result["management_residual"]=round(residual,2) if residual is not None else None;result["actual_performance"]=actual;result["expected_performance"]=expected;result["roster_attribution_factor"]=roster_change_penalty;result["timeout_effectiveness"]={"status":"not_available","reason":"No reliable timeout events/ticks"}
    return result

class LeadershipService:
    def __init__(self,session:AsyncSession):self.session=session
    async def team(self,team_id:int)->dict:
        team=await self.session.get(Team,team_id)
        if not team:raise ValueError("Команда не найдена.")
        memberships=(await self.session.execute(select(TeamParticipantMembership,Player).join(Player,Player.id==TeamParticipantMembership.player_id).where(TeamParticipantMembership.team_id==team_id,TeamParticipantMembership.is_active.is_(True),TeamParticipantMembership.left_at.is_(None)))).all()
        igl=next(((m,p) for m,p in memberships if m.participant_type=="player" and m.role=="igl"),None);coach=next(((m,p) for m,p in memberships if m.participant_type=="coach"),None)
        roster=await self.session.get(TeamRoster,team.current_roster_id) if team.current_roster_id else None
        rows=await self._aggregates(team_id,team.current_roster_id); allrows=[scopes["all"] for scopes in rows.values() if "all" in scopes];maps=sum(r.maps_played for r in allrows)
        strengths=[calculate_map_strength(scopes).map_strength_score for scopes in rows.values()];player_strengths=[float(p.player_strength) for m,p in memberships if m.participant_type=="player" and p.player_strength is not None]
        actual=mean([scope_performance(r) for r in allrows]);expected=expected_performance(player_strengths,[x for x in strengths if x is not None])
        tside=mean([num(r.t_win_rate) for r in allrows]);full=mean([nested(r.economy_data,"full_buy_vs_full_buy","win_rate") for r in allrows]);force=mean([nested(r.economy_data,"force_vs_full_buy","win_rate") for r in allrows]);anti=mean([nested(r.economy_data,"anti_eco","win_rate") for r in allrows]);conv=mean([nested(r.combat_data,"opening","conversion_rate") for r in allrows]);recovery=mean([nested(r.combat_data,"opening","recovery_rate") for r in allrows]);post=mean([num(r.postplant_win_rate) for r in allrows]);trade=mean([nested(r.combat_data,"trade","trade_rate") for r in allrows]);strong=mean([scope_performance(scopes.get("rank:top_15")) for scopes in rows.values()]+[scope_performance(scopes.get("rank:top_16_30")) for scopes in rows.values()])
        period_start=max([x for x in (roster.active_from if roster else None,igl[0].joined_at.date() if igl and igl[0].joined_at else None,coach[0].joined_at.date() if coach and coach[0].joined_at else None) if x is not None],default=None)
        igl_payload=calculate_igl(actual=actual,expected=expected,maps=maps,t_side=tside,full_buy=full,force_vs_full=force,anti_eco=anti,opening_conversion=conv,opening_recovery=recovery,postplant=post,trade=trade,strong=strong) if igl else None
        if igl_payload:igl_payload={"player_id":igl[1].id,"name":igl[1].nickname,"team_id":team_id,"roster_id":team.current_roster_id,"period":{"started_at":period_start,"ended_at":None,"source":"active membership + current roster"},**igl_payload,"player_strength":igl[1].player_strength,"captain_strength":round(igl[1].player_strength*.35+igl_payload["score"]*.65,2) if igl[1].player_strength is not None else None}
        coach_payload=None
        if coach:
            veto=await VetoService(self.session).profile(team_id,aggregation_level="current_roster");active_veto=[v for v in veto["maps"] if v["active"] and v["eligible_series"]]
            veto_quality=mean([mean([v["pick"]["win_rate"],v["opponent_pick"]["win_rate"],v["decider"]["win_rate"],100-v["permaban_confidence"] if v["pick_preference_score"] and v["pick_preference_score"]>60 else None]) for v in active_veto]) if active_veto else None
            developments=[];recent_values=[]
            for scopes in rows.values():
                base=scope_performance(scopes.get("all"));recent=next((scope_performance(scopes.get(f"recent:{n}")) for n in (5,10,20) if scopes.get(f"recent:{n}")),None)
                if base is not None and recent is not None:developments.append(clamp(50+(recent-base)*2));recent_values.append(recent-base)
            mapdev=mean(developments);prep=residual_score(strong,expected);consistency=clamp(100-pstdev(recent_values)*4) if len(recent_values)>=2 else None
            roster_factor=min(1,maps/10) if roster and roster.resolution_status=="complete" else .5
            coach_payload={"id":coach[1].id,"name":coach[1].nickname,"team_id":team_id,"roster_id":team.current_roster_id,"tenure":{"started_at":coach[0].joined_at.date() if coach[0].joined_at else roster.active_from if roster else None,"ended_at":None,"source":"active coach membership"},**calculate_coach(actual=actual,expected=expected,maps=maps,veto_quality=veto_quality,map_development=mapdev,opponent_prep=prep,player_development=None,consistency=consistency,roster_change_penalty=roster_factor)}
        return {"team":{"id":team.id,"name":team.name},"management_context":{"roster_id":team.current_roster_id,"period_started_at":period_start,"role_history_status":"current_only"},"igl":igl_payload,"coach":coach_payload}
    async def player(self,player_id:int)->dict|None:
        memberships=list((await self.session.execute(select(TeamParticipantMembership).where(TeamParticipantMembership.player_id==player_id,TeamParticipantMembership.is_active.is_(True),TeamParticipantMembership.left_at.is_(None),TeamParticipantMembership.participant_type=="player",TeamParticipantMembership.role=="igl"))).scalars())
        return await self.team(memberships[0].team_id) if memberships else None
    async def _aggregates(self,team_id:int,roster_id:int|None):
        if roster_id is None:return {}
        rows=list((await self.session.execute(select(TeamMapAggregate).where(TeamMapAggregate.team_id==team_id,TeamMapAggregate.aggregation_level=="roster",TeamMapAggregate.roster_id==roster_id))).scalars());out={}
        for row in rows:out.setdefault(row.map_name,{})[row.scope_key]=row
        return out
