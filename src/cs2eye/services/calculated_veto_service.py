from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.calculated_veto_config import (
    BAN_WEIGHTS, CALCULATED_VETO_MODEL_VERSION, H2H_MAX_WEIGHT, MATCHUP_WEIGHTS,
    PICK_WEIGHTS, ROSTER_PRIOR_MAPS, VETO_PRIOR_SERIES,
)
from cs2eye.analytics.scoring.core import FactorInput, sample_reliability, score_factors
from cs2eye.models.demo import TeamMapAggregate
from cs2eye.models.match import MapPoolEntry
from cs2eye.models.team import Team, TeamRosterMember
from cs2eye.services.round_swing_service import compose_roster_swing_profile, player_round_swing
from cs2eye.services.team_h2h_service import TeamH2HService
from cs2eye.services.team_map_strength_service import calculate_map_strength, scope_performance
from cs2eye.services.veto_service import VALID_MAPS, VetoService

DEFAULT_ACTIVE_POOL = {"ancient", "dust2", "inferno", "mirage", "nuke", "overpass", "train"}

def clamp(value: float) -> float: return max(0.0, min(100.0, value))
def number(value: Any) -> float | None: return float(value) if value is not None else None
def avg(values: list[float | None]) -> float | None:
    present=[v for v in values if v is not None]
    return sum(present)/len(present) if present else None
def cross(own: float | None, opponent: float | None) -> float | None:
    if own is None or opponent is None:return None
    return clamp(50+(own-opponent)/2)
def nested(data:dict|None,*keys:str)->float|None:
    value:Any=data
    for key in keys:
        if not isinstance(value,dict):return None
        value=value.get(key)
    return number(value)

@dataclass
class MapSignals:
    strength: float | None = None; strength_confidence: float = 0
    maps: int = 0; freshness: float = 0
    recent: float | None = None; top15: float | None = None; top16_30: float | None = None
    ct: float | None = None; t: float | None = None
    postplant: float | None = None; retake: float | None = None
    economy: dict | None = None; combat: dict | None = None; utility: dict | None = None
    swing: dict | None = None
    pick_preference: float | None = None; ban_preference: float | None = None
    recent_pick_preference: float | None = None; veto_series: int = 0
    h2h_score: float | None = None; h2h_maps: int = 0; roster_share: float = 0

def blend_signals(org:MapSignals,roster:MapSignals|None)->MapSignals:
    if not roster or roster.maps<=0:return org
    share=sample_reliability(roster.maps,ROSTER_PRIOR_MAPS)
    def blend(a:float|None,b:float|None)->float|None:
        if b is None:return a
        if a is None:return b
        return a*(1-share)+b*share
    result=MapSignals(**org.__dict__); result.roster_share=share
    for key in ("strength","strength_confidence","freshness","recent","top15","top16_30","ct","t","postplant","retake"):
        setattr(result,key,blend(getattr(org,key),getattr(roster,key)))
    result.maps=org.maps+roster.maps
    result.economy=roster.economy if share>=.5 and roster.economy else org.economy
    result.combat=roster.combat if share>=.5 and roster.combat else org.combat
    result.utility=roster.utility if share>=.5 and roster.utility else org.utility
    result.swing=roster.swing or org.swing
    return result

def factors_payload(result)->list[dict]: return [{**f.__dict__,"score":f.normalized_score} for f in result.factors]

def calculate_map_pair(a:MapSignals,b:MapSignals)->dict:
    relative_a=clamp(50+((a.strength or 50)-(b.strength or 50))*1.5) if a.strength is not None and b.strength is not None else None
    relative_b=100-relative_a if relative_a is not None else None
    side_a=avg([cross(a.t,b.ct),cross(a.ct,b.t)]); side_b=avg([cross(b.t,a.ct),cross(b.ct,a.t)])
    bomb_a=avg([cross(a.postplant,b.retake),cross(a.retake,b.postplant)]); bomb_b=avg([cross(b.postplant,a.retake),cross(b.retake,a.postplant)])
    def composite(x:MapSignals,y:MapSignals)->float|None:
        def weighted(items:list[tuple[float|None,float]])->float|None:
            present=[(value,weight) for value,weight in items if value is not None]
            return sum(value*weight for value,weight in present)/sum(weight for _,weight in present) if present else None
        economy=avg([nested(x.economy,"full_buy_vs_full_buy","win_rate"),nested(x.economy,"force_buy","win_rate"),nested(x.economy,"anti_eco","win_rate"),nested(x.economy,"pistol","win_rate"),nested(x.economy,"conversion","win_rate")])
        # V1.1 keeps trade rate as coordination evidence, while Round Swing takes over
        # most of the duplicated kill/opening/clutch impact inside this existing factor.
        combat=weighted([
            (nested(x.swing,"avg_score"),.45),
            (nested(x.combat,"opening","success_rate"),.12),
            (nested(x.combat,"opening","conversion_rate"),.08),
            (nested(x.combat,"trade","trade_rate"),.20),
            (nested(x.combat,"clutch","win_rate"),.05),
        ])
        enemy=avg([nested(y.economy,"full_buy_vs_full_buy","win_rate"),nested(y.swing,"avg_score"),nested(y.combat,"trade","trade_rate")])
        return cross(avg([economy,combat]),enemy)
    ec_a,ec_b=composite(a,b),composite(b,a)
    def economy_only(x:MapSignals,y:MapSignals)->float|None:
        own=avg([nested(x.economy,"full_buy_vs_full_buy","win_rate"),nested(x.economy,"force_buy","win_rate"),nested(x.economy,"anti_eco","win_rate"),nested(x.economy,"pistol","win_rate"),nested(x.economy,"conversion","win_rate")])
        opp=avg([nested(y.economy,"full_buy_vs_full_buy","win_rate"),nested(y.economy,"force_buy","win_rate"),nested(y.economy,"anti_eco","win_rate"),nested(y.economy,"pistol","win_rate"),nested(y.economy,"conversion","win_rate")])
        return cross(own,opp)
    def combat_only(x:MapSignals,y:MapSignals)->float|None:
        own=avg([nested(x.swing,"avg_score"),nested(x.combat,"opening","success_rate"),nested(x.combat,"opening","recovery_rate"),nested(x.combat,"clutch","win_rate")])
        opp=avg([nested(y.swing,"avg_score"),nested(y.combat,"opening","success_rate"),nested(y.combat,"opening","recovery_rate"),nested(y.combat,"clutch","win_rate")])
        return cross(own,opp)
    def trading_only(x:MapSignals,y:MapSignals)->float|None:
        return cross(nested(x.combat,"trade","trade_rate"),nested(y.combat,"trade","trade_rate"))
    def utility(x:MapSignals,y:MapSignals)->float|None:
        # Rate-like utility fields are compared relatively; damage is normalized around 8 dmg/round.
        own=avg([nested(x.utility,"enemies_flashed_per_flash"),nested(x.utility,"flash_assists_per_round"),nested(x.utility,"utility_damage_per_round")])
        opp=avg([nested(y.utility,"enemies_flashed_per_flash"),nested(y.utility,"flash_assists_per_round"),nested(y.utility,"utility_damage_per_round")])
        return cross(own,opp)
    util_a,util_b=utility(a,b),utility(b,a)
    def side(x:MapSignals,relative:float|None,side_score,bomb,ec,util):
        form=avg([x.recent,x.top15,x.top16_30])
        swing_reason=("Round Swing, reduced raw opening/clutch, trade coordination and economy; "
                      f"roster Swing {nested(x.swing,'avg_score'):.1f}" if nested(x.swing,"avg_score") is not None
                      else "Economy/combat fallback; Round Swing unavailable and receives no zero penalty")
        inputs=[FactorInput("own_map_quality","Own map quality",x.strength,x.strength,MATCHUP_WEIGHTS["own_map_quality"],x.maps,x.strength_confidence/100,"Existing Map Strength with reliability"),FactorInput("relative_advantage","Relative advantage",relative,relative,MATCHUP_WEIGHTS["relative_advantage"],reason="Normalized own minus opponent Map Strength"),FactorInput("recent_roster_form","Recent/current-roster form",form,form,MATCHUP_WEIGHTS["recent_roster_form"],x.maps,reason=f"Recent scopes and roster blend; roster share {x.roster_share:.2f}"),FactorInput("side_matchup","CT/T cross-matchup",side_score,side_score,MATCHUP_WEIGHTS["side_matchup"],reason="T vs opponent CT and CT vs opponent T"),FactorInput("bomb_matchup","Postplant/retake cross-matchup",bomb,bomb,MATCHUP_WEIGHTS["bomb_matchup"],reason="Postplant vs opponent retake, and reverse"),FactorInput("economy_combat_matchup","Economy/combat matchup",ec,ec,MATCHUP_WEIGHTS["economy_combat_matchup"],reason=swing_reason),FactorInput("utility_teamplay_matchup","Utility/teamplay matchup",util,util,MATCHUP_WEIGHTS["utility_teamplay_matchup"])]
        metric_coverage=sum(i.normalized_score is not None for i in inputs)/len(inputs)
        reliability=clamp((x.strength_confidence*.45+x.freshness*.2+min(100,x.maps*8)*.2+metric_coverage*100*.15)/100)
        result=score_factors(inputs,reliability)
        # H2H is a bounded post-factor: max 8%, reliability saturates only after 5 maps.
        hrel=min(1,x.h2h_maps/5)*H2H_MAX_WEIGHT
        final=clamp(result.final_score*(1-hrel)+(x.h2h_score or 50)*hrel)
        return final,result,relative,metric_coverage
    ma,mab,ra,cova=side(a,relative_a,side_a,bomb_a,ec_a,util_a); mb,mbb,rb,covb=side(b,relative_b,side_b,bomb_b,ec_b,util_b)
    def actions(x:MapSignals,matchup:float,relative:float|None,opp:MapSignals):
        pick_inputs=[FactorInput("matchup_map_score","Matchup map score",matchup,matchup,PICK_WEIGHTS["matchup_map_score"]),FactorInput("relative_advantage","Relative advantage",relative,relative,PICK_WEIGHTS["relative_advantage"]),FactorInput("historical_pick_preference","Historical pick preference",x.pick_preference,x.pick_preference,PICK_WEIGHTS["historical_pick_preference"],x.veto_series),FactorInput("recent_veto_preference","Recent veto preference",x.recent_pick_preference,x.recent_pick_preference,PICK_WEIGHTS["recent_veto_preference"],min(x.veto_series,5))]
        ban_inputs=[FactorInput("own_weakness","Own weakness",None if x.strength is None else 100-x.strength,None if x.strength is None else 100-x.strength,BAN_WEIGHTS["own_weakness"]),FactorInput("opponent_map_threat","Opponent map threat",opp.strength,opp.strength,BAN_WEIGHTS["opponent_map_threat"]),FactorInput("relative_disadvantage","Relative disadvantage",None if relative is None else 100-relative,None if relative is None else 100-relative,BAN_WEIGHTS["relative_disadvantage"]),FactorInput("historical_ban_preference","Historical ban preference",x.ban_preference,x.ban_preference,BAN_WEIGHTS["historical_ban_preference"],x.veto_series)]
        vreliability=sample_reliability(x.veto_series,VETO_PRIOR_SERIES)
        confidence=clamp((x.strength_confidence/100*.55+min(1,x.maps/10)*.25+vreliability*.20))
        return score_factors(pick_inputs,confidence),score_factors(ban_inputs,confidence),confidence
    pa,ba,ca=actions(a,ma,ra,b);pb,bb,cb=actions(b,mb,rb,a)
    def payload(matchup,mbreak,pick,ban,conf,signals):return {"matchup_map_score":round(matchup,2),"calculated_pick_score":pick.final_score,"calculated_ban_score":ban.final_score,"matchup_confidence":mbreak.reliability,"pick_confidence":pick.reliability,"ban_confidence":ban.reliability,"matchup_factors":factors_payload(mbreak),"pick_factors":factors_payload(pick),"ban_factors":factors_payload(ban),"roster_form":{"recent":signals.recent,"roster_share":signals.roster_share,"maps":signals.maps,"freshness":signals.freshness}}
    collision=max(pa.final_score*bb.final_score/100,pb.final_score*ba.final_score/100)
    tactical_a={"side":side_a,"bomb":bomb_a,"combat_swing":combat_only(a,b),"economy":economy_only(a,b),"utility":util_a,"trading":trading_only(a,b),"swing_profile":a.swing}
    tactical_b={"side":side_b,"bomb":bomb_b,"combat_swing":combat_only(b,a),"economy":economy_only(b,a),"utility":util_b,"trading":trading_only(b,a),"swing_profile":b.swing}
    return {"team_a":{**payload(ma,mab,pa,ba,ca,a),"tactical_components":tactical_a},"team_b":{**payload(mb,mbb,pb,bb,cb,b),"tactical_components":tactical_b},"collision_score":round(collision,2),"collision":"high" if collision>=60 else "medium" if collision>=35 else "low"}

def simulate(maps:list[dict],first_side:str)->dict:
    remaining={m["map"]:m for m in maps}; other={"team_a":"team_b","team_b":"team_a"}; second=other[first_side]; actions=[]
    for side,kind in ((first_side,"ban"),(second,"ban"),(first_side,"pick"),(second,"pick"),(first_side,"ban"),(second,"ban")):
        key="calculated_ban_score" if kind=="ban" else "calculated_pick_score"
        chosen=max(remaining.values(),key=lambda m:(m[side][key],m["map"])); actions.append({"order":len(actions)+1,"team":side,"action":kind,"map":chosen["map"],"effective_action_score":chosen[side][key]});remaining.pop(chosen["map"])
    if remaining:actions.append({"order":len(actions)+1,"team":None,"action":"decider","map":sorted(remaining)[0],"effective_action_score":None})
    return {"first_actor":first_side,"actions":actions}

class CalculatedVetoService:
    def __init__(self,session:AsyncSession,today:date|None=None):self.session=session;self.today=today or date.today()
    async def calculate(self,a_id:int,b_id:int,format:str="bo3",first_actor:str|None=None)->dict:
        if a_id==b_id:raise ValueError("Нужны две разные команды.")
        teams=[await self.session.get(Team,x) for x in (a_id,b_id)]
        if any(t is None for t in teams):raise ValueError("Команда не найдена.")
        active=list((await self.session.execute(select(MapPoolEntry.map_name).where(MapPoolEntry.is_active.is_(True)))).scalars());pool=set(active) or DEFAULT_ACTIVE_POOL
        if format!="bo3":raise ValueError("Calculated Veto v1 поддерживает deterministic simulation только для BO3.")
        veto_profiles=[await VetoService(self.session).profile(x,aggregation_level="organization") for x in (a_id,b_id)]
        veto_recent=[await VetoService(self.session).profile(x,aggregation_level="organization",recent=5) for x in (a_id,b_id)]
        h2h=await TeamH2HService(self.session,today=self.today).compare(a_id,b_id,recent_limit=20)
        signals=[]
        for idx,team_id in enumerate((a_id,b_id)):
            org=await self._load(team_id,"organization",None); roster=await self._load(team_id,"roster",teams[idx].current_roster_id)
            if teams[idx].current_roster_id:
                player_ids=list((await self.session.execute(select(TeamRosterMember.player_id).where(
                    TeamRosterMember.roster_id==teams[idx].current_roster_id,
                    TeamRosterMember.player_id.is_not(None)))).scalars())
                swing_players=[{"player_id":player_id,**await player_round_swing(self.session,player_id)} for player_id in player_ids]
                for map_name,value in roster.items():
                    profile=compose_roster_swing_profile(swing_players,map_name)
                    if profile.get("status") not in {"not_calculated"}:
                        value.swing=profile
            vp={m["map_name"]:m for m in veto_profiles[idx]["maps"]};vr={m["map_name"]:m for m in veto_recent[idx]["maps"]}
            horg={m.map_name:m for m in h2h.organizations.maps};hcur={m.map_name:m for m in h2h.current_rosters.maps}
            combined={}
            for name in pool:
                value=blend_signals(org.get(name,MapSignals()),roster.get(name));v=vp.get(name);rv=vr.get(name)
                if v:value.pick_preference=v["pick_preference_score"];value.ban_preference=v["permaban_confidence"];value.veto_series=v["eligible_series"]
                if rv:value.recent_pick_preference=rv["pick_preference_score"]
                hm=hcur.get(name) if h2h.current_rosters.maps_played>=3 else horg.get(name)
                if hm:
                    value.h2h_maps=hm.maps_played;value.h2h_score=(hm.team_a_map_win_rate if idx==0 else hm.team_b_map_win_rate)
                combined[name]=value
            signals.append(combined)
        maps=[]
        for name in sorted(pool):maps.append({"map":name,"active":True,**calculate_map_pair(signals[0][name],signals[1][name])})
        actors=[first_actor] if first_actor else ["team_a","team_b"]
        if any(x not in {"team_a","team_b"} for x in actors):raise ValueError("first_actor must be team_a or team_b")
        return {"calculated_veto_model_version":CALCULATED_VETO_MODEL_VERSION,"score_semantics":"analytical_score_0_100_not_probability","format":format,"veto_format_assumption":"standard_bo3","first_actor_known":first_actor is not None,"team_a":{"id":teams[0].id,"name":teams[0].name},"team_b":{"id":teams[1].id,"name":teams[1].name},"maps":maps,"scenarios":[simulate(maps,x) for x in actors]}
    async def _load(self,team_id:int,level:str,roster_id:int|None)->dict[str,MapSignals]:
        if level=="roster" and roster_id is None:return {}
        q=select(TeamMapAggregate).where(TeamMapAggregate.team_id==team_id,TeamMapAggregate.aggregation_level==level)
        q=q.where(TeamMapAggregate.roster_id==roster_id) if level=="roster" else q.where(TeamMapAggregate.roster_id.is_(None))
        rows=list((await self.session.execute(q)).scalars());grouped={}
        for row in rows:grouped.setdefault(row.map_name,{})[row.scope_key]=row
        out={}
        for name,scopes in grouped.items():
            allrow=scopes.get("all")
            if not allrow:continue
            strength=calculate_map_strength(scopes,self.today);recent=next((scope_performance(scopes.get(f"recent:{n}")) for n in (5,10,20) if scopes.get(f"recent:{n}") and scopes[f"recent:{n}"].maps_played>=3),None)
            out[name]=MapSignals(strength.map_strength_score,strength.confidence_score,allrow.maps_played,number(allrow.freshness_score) or 0,recent,scope_performance(scopes.get("rank:top_15")),scope_performance(scopes.get("rank:top_16_30")),number(allrow.ct_win_rate),number(allrow.t_win_rate),number(allrow.postplant_win_rate),number(allrow.retake_win_rate),allrow.economy_data,allrow.combat_data,allrow.utility_data)
        return out
    async def backtest(self,match_id:int)->dict:
        from cs2eye.models.match import Match
        match=await self.session.get(Match,match_id)
        if not match or not match.team_a_id or not match.team_b_id:raise ValueError("Серия не найдена или команды неизвестны.")
        calculated=await self.calculate(match.team_a_id,match.team_b_id,match.format)
        actual=await VetoService(self.session).actions(match_id)
        return {"match_id":match_id,"model_version":CALCULATED_VETO_MODEL_VERSION,"calculated":calculated,"actual":[{"order":x.order_index,"team_id":x.team_id,"action":x.action,"map":x.map_name} for x in actual]}
