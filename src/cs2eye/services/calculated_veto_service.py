from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import log
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.calculated_veto_config import (
    BAN_WEIGHTS, CALCULATED_VETO_MODEL_VERSION, H2H_MAX_WEIGHT, MATCHUP_WEIGHTS,
    PICK_WEIGHTS, ROSTER_PRIOR_MAPS, VETO_PRIOR_SERIES, VETO_ROSTER_PRIOR_SERIES,
    VETO_RECENT_PRIOR_SERIES, VETO_V2_WEIGHTS, VETO_CONFIDENCE_PRIOR_SERIES,
    VETO_ACTOR_PRIOR_SERIES,
)
from cs2eye.analytics.scoring.core import FactorInput, sample_reliability, score_factors
from cs2eye.models.demo import TeamMapAggregate
from cs2eye.models.match import MapPoolEntry
from cs2eye.models.team import Team, TeamRosterMember
from cs2eye.services.round_swing_service import compose_roster_swing_profile, player_round_swing
from cs2eye.services.team_h2h_service import TeamH2HService
from cs2eye.services.team_map_strength_service import calculate_map_strength, scope_performance
from cs2eye.services.veto_service import VALID_MAPS, VetoService

DEFAULT_ACTIVE_POOL = {
    "ancient", "anubis", "cache", "dust2", "inferno", "mirage", "nuke",
}

def bounded_probabilities(values: list[float], expected: float = 3.0) -> list[float]:
    """Project non-negative marginals onto [0,1] with an exact expected sum."""
    if not values:return []
    target=min(float(len(values)),max(0.0,expected)); remaining=set(range(len(values)))
    result=[0.0]*len(values); remainder=target
    while remaining:
        total=sum(max(0.0,values[i]) for i in remaining)
        proposed={i:(remainder/len(remaining) if total<=0 else max(0.0,values[i])*remainder/total) for i in remaining}
        capped=[i for i,value in proposed.items() if value>=1.0]
        if not capped:
            for i,value in proposed.items():result[i]=value
            break
        for i in capped:result[i]=1.0;remainder-=1.0;remaining.remove(i)
    return result

def _blend_rate(org: dict, roster: dict | None, recent: dict | None, key: str, baseline: float) -> float:
    def get(row:dict|None)->float|None:
        value=nested(row,*key.split("."))
        return None if value is None else value/100
    value=get(org)
    value=baseline if value is None else value
    if roster and (candidate:=get(roster)) is not None:
        share=sample_reliability(roster.get("eligible_series",0),VETO_ROSTER_PRIOR_SERIES)
        value=value*(1-share)+candidate*share
    if recent and (candidate:=get(recent)) is not None:
        share=sample_reliability(recent.get("eligible_series",0),VETO_RECENT_PRIOR_SERIES)
        value=value*(1-share)+candidate*share
    return value

def action_propensity(org:dict,roster:dict|None,recent:dict|None,role:str,actor_scope:str,prior:float)->tuple[float,float]:
    overall=_blend_rate(org,roster,recent,f"{role}.rate",prior)
    effective_sample=org.get("eligible_series",0)+(roster or {}).get("eligible_series",0)*.5+(recent or {}).get("eligible_series",0)*.25
    reliability=sample_reliability(effective_sample,VETO_CONFIDENCE_PRIOR_SERIES)
    value=prior*(1-reliability)+overall*reliability
    scopes=[source.get(actor_scope) for source in (org,roster,recent) if source and source.get(actor_scope)]
    actor_sample=sum(scope.get("eligible_series",0) for scope in scopes)
    actor_values=[nested(scope,role,"rate") for scope in scopes]
    actor_values=[x/100 for x in actor_values if x is not None]
    actor_reliability=sample_reliability(actor_sample,VETO_ACTOR_PRIOR_SERIES)
    if actor_values:value=value*(1-actor_reliability)+sum(actor_values)/len(actor_values)*actor_reliability
    return max(1e-6,value),min(1.0,reliability*.8+actor_reliability*.2)

def veto_raw_probability(selected_a:float,selected_b:float,pick_a:float,pick_b:float,ban_a:float,ban_b:float,map_quality:float)->tuple[float,dict[str,float]]:
    components={
        "historical_selection":(selected_a+selected_b)/2,
        "pick_pressure":(pick_a+pick_b)/2,
        "ban_survival":(1-ban_a)*(1-ban_b),
        "map_matchup_quality":map_quality,
    }
    return sum(components[key]*weight for key,weight in VETO_V2_WEIGHTS.items()),components

def exact_veto_tree(pool:set[str],propensities:dict[str,dict[str,dict[str,float]]],first_side:str,*,debug:bool=False)->dict:
    """Enumerate the exact conditional standard-BO3 veto tree."""
    if len(pool)!=7:raise ValueError("Exact standard BO3 veto tree requires a 7-map pool.")
    second="team_b" if first_side=="team_a" else "team_a"
    steps=((first_side,"opening_ban"),(second,"opening_ban"),(first_side,"pick"),(second,"pick"),(first_side,"closing_ban"),(second,"closing_ban"))
    maps={name:{"opening_ban_probability":0.0,"pick_by_team_a_probability":0.0,"pick_by_team_b_probability":0.0,"closing_ban_probability":0.0,"decider_probability":0.0} for name in pool}
    opening={"team_a":{name:0.0 for name in pool},"team_b":{name:0.0 for name in pool}}
    debug_states=[];branch_mass=0.0
    def walk(index:int,remaining:tuple[str,...],mass:float,actions:list[dict])->None:
        nonlocal branch_mass
        if index==len(steps):
            if len(remaining)!=1:raise ValueError("Invalid veto branch: expected exactly one decider.")
            maps[remaining[0]]["decider_probability"]+=mass;branch_mass+=mass
            return
        side,role=steps[index];scores={name:max(1e-9,propensities[side][role][name]) for name in remaining};total=sum(scores.values())
        distribution={name:scores[name]/total for name in remaining}
        if debug:debug_states.append({"step":index+1,"team":side,"action":role,"remaining":list(remaining),"branch_probability":mass,"probabilities":distribution})
        for name,conditional in distribution.items():
            next_mass=mass*conditional
            if role=="opening_ban":maps[name]["opening_ban_probability"]+=next_mass;opening[side][name]+=next_mass
            elif role=="closing_ban":maps[name]["closing_ban_probability"]+=next_mass
            else:maps[name][f"pick_by_{side}_probability"]+=next_mass
            walk(index+1,tuple(x for x in remaining if x!=name),next_mass,actions+[{"team":side,"action":role,"map":name}])
    walk(0,tuple(sorted(pool)),1.0,[])
    for item in maps.values():
        item["pick_probability"]=item["pick_by_team_a_probability"]+item["pick_by_team_b_probability"]
        item["any_ban_probability"]=item["opening_ban_probability"]+item["closing_ban_probability"]
        item["opening_ban_survival_probability"]=1-item["opening_ban_probability"]
        item["series_map_probability"]=item["pick_probability"]+item["decider_probability"]
    result={"branch_probability_sum":branch_mass,"maps":maps,"opening_bans":opening}
    if debug:result["debug_steps"]=debug_states
    validate_tree_invariants(result)
    return result

def validate_tree_invariants(result:dict,tolerance:float=1e-8)->None:
    rows=list(result["maps"].values())
    checks=((result["branch_probability_sum"],1),(sum(x["opening_ban_probability"] for x in rows),2),(sum(x["pick_probability"] for x in rows),2),(sum(x["closing_ban_probability"] for x in rows),2),(sum(x["decider_probability"] for x in rows),1),(sum(x["series_map_probability"] for x in rows),3))
    if any(abs(actual-expected)>tolerance for actual,expected in checks) or any(abs(x["series_map_probability"]+x["any_ban_probability"]-1)>tolerance for x in rows):raise ValueError("Invalid exact veto tree probability invariants.")

def mix_veto_trees(trees:list[tuple[float,dict]])->dict:
    total=sum(weight for weight,_ in trees)
    if not trees or abs(total-1)>1e-9:raise ValueError("Veto tree mixture weights must sum to one.")
    names=trees[0][1]["maps"].keys();sides=("team_a","team_b")
    result={"branch_probability_sum":sum(weight*tree["branch_probability_sum"] for weight,tree in trees),"maps":{},"opening_bans":{side:{} for side in sides}}
    for name in names:
        result["maps"][name]={key:sum(weight*tree["maps"][name][key] for weight,tree in trees) for key in trees[0][1]["maps"][name]}
        for side in sides:result["opening_bans"][side][name]=sum(weight*tree["opening_bans"][side][name] for weight,tree in trees)
    validate_tree_invariants(result);return result

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
    async def calculate(self,a_id:int,b_id:int,format:str="bo3",first_actor:str|None=None,*,as_of:date|None=None,map_pool_version:str|None=None,exclude_match_id:int|None=None,debug:bool=False)->dict:
        if a_id==b_id:raise ValueError("Нужны две разные команды.")
        teams=[await self.session.get(Team,x) for x in (a_id,b_id)]
        if any(t is None for t in teams):raise ValueError("Команда не найдена.")
        pool_query=select(MapPoolEntry.map_name)
        if map_pool_version:pool_query=pool_query.where(MapPoolEntry.version==map_pool_version)
        else:pool_query=pool_query.where(MapPoolEntry.is_active.is_(True))
        pool=set((await self.session.execute(pool_query)).scalars())
        if not pool:raise ValueError("Активный map pool не настроен." if not map_pool_version else "Версия map pool не найдена.")
        if format!="bo3":raise ValueError("Calculated Veto v2.1 поддерживает probability estimate для BO3.")
        veto=VetoService(self.session)
        veto_profiles=[await veto.profile(x,aggregation_level="organization",as_of=as_of,exclude_match_id=exclude_match_id,veto_format="bo3") for x in (a_id,b_id)]
        veto_rosters=[await veto.profile(x,aggregation_level="current_roster",as_of=as_of,exclude_match_id=exclude_match_id,veto_format="bo3") for x in (a_id,b_id)]
        veto_recents=[]
        for x in (a_id,b_id):
            candidates=[await veto.profile(x,aggregation_level="organization",recent=n,as_of=as_of,exclude_match_id=exclude_match_id,veto_format="bo3") for n in (5,10,20)]
            veto_recents.append(next((p for p in candidates if p["sample"]["series"]>=3),None))
        historical=as_of is not None and as_of < date.today()
        h2h=None if historical else await TeamH2HService(self.session,today=self.today).compare(a_id,b_id,recent_limit=20)
        signals=[]
        for idx,team_id in enumerate((a_id,b_id)):
            org={} if historical else await self._load(team_id,"organization",None); roster={} if historical else await self._load(team_id,"roster",teams[idx].current_roster_id)
            if teams[idx].current_roster_id:
                player_ids=list((await self.session.execute(select(TeamRosterMember.player_id).where(
                    TeamRosterMember.roster_id==teams[idx].current_roster_id,
                    TeamRosterMember.player_id.is_not(None)))).scalars())
                swing_players=[{"player_id":player_id,**await player_round_swing(self.session,player_id)} for player_id in player_ids]
                for map_name,value in roster.items():
                    profile=compose_roster_swing_profile(swing_players,map_name)
                    if profile.get("status") not in {"not_calculated"}:
                        value.swing=profile
            vp={m["map_name"]:m for m in veto_profiles[idx]["maps"]};vr={m["map_name"]:m for m in (veto_recents[idx] or {"maps":[]})["maps"]}
            horg={m.map_name:m for m in h2h.organizations.maps} if h2h else {};hcur={m.map_name:m for m in h2h.current_rosters.maps} if h2h else {}
            combined={}
            for name in pool:
                value=blend_signals(org.get(name,MapSignals()),roster.get(name));v=vp.get(name);rv=vr.get(name)
                if v:value.pick_preference=v["pick_preference_score"];value.ban_preference=v["permaban_confidence"];value.veto_series=v["eligible_series"]
                if rv:value.recent_pick_preference=rv["pick_preference_score"]
                hm=hcur.get(name) if h2h and h2h.current_rosters.maps_played>=3 else horg.get(name)
                if hm:
                    value.h2h_maps=hm.maps_played;value.h2h_score=(hm.team_a_map_win_rate if idx==0 else hm.team_b_map_win_rate)
                combined[name]=value
            signals.append(combined)
        actor_aliases={"team_a":"team_a","team_b":"team_b",str(a_id):"team_a",str(b_id):"team_b",teams[0].name.casefold():"team_a",teams[1].name.casefold():"team_b"}
        first_side=actor_aliases.get(first_actor.casefold()) if first_actor else None
        if first_actor and first_side is None:raise ValueError("first_actor must identify team_a or team_b")
        org_maps=[{m["map_name"]:m for m in p["maps"]} for p in veto_profiles]
        roster_maps=[{m["map_name"]:m for m in p["maps"]} for p in veto_rosters]
        recent_maps=[{m["map_name"]:m for m in (p or {"maps":[]})["maps"]} for p in veto_recents]
        baseline=3/len(pool);maps=[];diagnostics={};sources={side:{} for side in ("team_a","team_b")}
        for name in sorted(pool):
            diagnostic=calculate_map_pair(signals[0][name],signals[1][name])
            diagnostics[name]=diagnostic
            histories=[]
            for idx in (0,1):
                o=org_maps[idx].get(name,{"eligible_series":0});r=roster_maps[idx].get(name);recent=recent_maps[idx].get(name)
                sources[("team_a","team_b")[idx]][name]=(o,r,recent)
                histories.append({"selected_rate":_blend_rate(o,r,recent,"selected.rate",baseline),"pick_rate":_blend_rate(o,r,recent,"pick.rate",0),"ban_rate":_blend_rate(o,r,recent,"ban.rate",1-baseline)})
            quality=(diagnostic["team_a"]["matchup_map_score"]+diagnostic["team_b"]["matchup_map_score"])/200
            raw,components=veto_raw_probability(histories[0]["selected_rate"],histories[1]["selected_rate"],histories[0]["pick_rate"],histories[1]["pick_rate"],histories[0]["ban_rate"],histories[1]["ban_rate"],quality)
            org_n=min(p["sample"]["series"] for p in veto_profiles);roster_n=min(p["sample"]["series"] for p in veto_rosters);recent_n=min((p or {"sample":{"series":0}})["sample"]["series"] for p in veto_recents)
            completeness=min((p["sample"]["complete_series"]/p["sample"]["series"] if p["sample"]["series"] else 0) for p in veto_profiles)
            coverage=sum(any(nested(org_maps[i].get(name),*k.split(".")) is not None for i in (0,1)) for k in ("selected.rate","pick.rate","ban.rate"))/3
            sample_rel=sample_reliability(org_n+roster_n*.5+recent_n*.25,VETO_CONFIDENCE_PRIOR_SERIES)
            freshness=min(p["veto_confidence"] for p in veto_profiles)/100
            confidence=clamp(100*(sample_rel*.45+freshness*.2+completeness*.2+coverage*.15))/100
            maps.append({"map":name,"active":True,"confidence":round(confidence,4),"components":{k:round(v,4) for k,v in components.items()},"team_a_history":{k:round(v,4) for k,v in histories[0].items()},"team_b_history":{k:round(v,4) for k,v in histories[1].items()},"history_samples":{"team_a":{"organization":veto_profiles[0]["sample"]["series"],"current_roster":veto_rosters[0]["sample"]["series"],"recent":(veto_recents[0] or {"sample":{"series":0}})["sample"]["series"]},"team_b":{"organization":veto_profiles[1]["sample"]["series"],"current_roster":veto_rosters[1]["sample"]["series"],"recent":(veto_recents[1] or {"sample":{"series":0}})["sample"]["series"]}},**diagnostic})
        action_reliability={name:[] for name in pool}
        def propensities(order_first:str)->dict:
            result={side:{role:{} for role in ("opening_ban","pick","closing_ban")} for side in ("team_a","team_b")}
            for side in ("team_a","team_b"):
                scope="when_first_actor" if side==order_first else "when_second_actor"
                for name in pool:
                    diagnostic=diagnostics[name][side];o,r,recent=sources[side][name]
                    priors={"opening_ban":diagnostic["calculated_ban_score"]/100,"closing_ban":diagnostic["calculated_ban_score"]/100,"pick":diagnostic["calculated_pick_score"]/100}
                    for role in result[side]:
                        value,reliability=action_propensity(o,r,recent,role,scope,priors[role])
                        result[side][role][name]=value;action_reliability[name].append(reliability)
            return result
        orders=[first_side] if first_side else ["team_a","team_b"]
        tree_parts=[];debug_payload=[]
        for order in orders:
            tree=exact_veto_tree(pool,propensities(order),order,debug=debug)
            tree_parts.append((1/len(orders),tree))
            if debug:debug_payload.append({"first_actor":order,"steps":tree.get("debug_steps",[])})
        tree=tree_parts[0][1] if len(tree_parts)==1 else mix_veto_trees(tree_parts)
        for item in maps:
            item.update(tree["maps"][item["map"]]);item["confidence"]=round((item["confidence"]+avg(action_reliability[item["map"]]))/2,4)
        maps.sort(key=lambda x:(-x["series_map_probability"],x["map"]))
        for rank,item in enumerate(maps,1):item["rank"]=rank
        opening={side:[{"map":name,"probability":probability} for name,probability in sorted(tree["opening_bans"][side].items(),key=lambda x:(-x[1],x[0]))] for side in ("team_a","team_b")}
        response={"calculated_veto_model_version":CALCULATED_VETO_MODEL_VERSION,"method":"exact_conditional_veto_tree","probability_semantics":"heuristic_estimate_not_calibrated","format":format,"first_actor":first_side,"first_actor_assumption":None if first_side else "unknown_equal_50_50","team_a":{"id":teams[0].id,"name":teams[0].name},"team_b":{"id":teams[1].id,"name":teams[1].name},"pool_size":len(pool),"expected_selected_maps":3,"map_pool_version":map_pool_version,"branch_probability_sum":tree["branch_probability_sum"],"maps":maps,"opening_bans":opening}
        if debug:response["debug"]={"orders":debug_payload}
        return response
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
        if match.format!="bo3" or not match.map_pool_version:raise ValueError("Backtest требует BO3 с map_pool_version.")
        actual=await VetoService(self.session).actions(match_id)
        first_action=next((x for x in actual if x.team_id is not None),None)
        first_actor="team_a" if first_action and first_action.team_id==match.team_a_id else "team_b" if first_action else None
        calculated=await self.calculate(match.team_a_id,match.team_b_id,"bo3",first_actor,as_of=match.match_date,map_pool_version=match.map_pool_version,exclude_match_id=match.id)
        selected={x.map_name for x in actual if x.action in {"pick","decider"}}
        if len(selected)!=3:raise ValueError("Для backtest нужен complete veto с тремя выбранными картами.")
        rows=[]
        for item in calculated["maps"]:
            label=int(item["map"] in selected);p=item["series_map_probability"]
            rows.append({"map":item["map"],"predicted_rank":item["rank"],"actual_selected":label,"predicted_probability":p,"confidence":item["confidence"]})
        baseline=3/calculated["pool_size"]
        def metrics(probabilities:list[float])->tuple[float,float]:
            labels=[row["actual_selected"] for row in rows]
            brier=sum((p-y)**2 for p,y in zip(probabilities,labels))/len(labels)
            loss=-sum(y*log(max(1e-12,min(1-1e-12,p)))+(1-y)*log(max(1e-12,min(1-1e-12,1-p))) for p,y in zip(probabilities,labels))/len(labels)
            return round(brier,6),round(loss,6)
        brier,loss=metrics([r["predicted_probability"] for r in rows]);base_brier,base_loss=metrics([baseline]*len(rows))
        hits=sum(r["actual_selected"] for r in rows if r["predicted_rank"]<=3)
        team_ids={"team_a":match.team_a_id,"team_b":match.team_b_id}
        actual_opening={side:next((x.map_name for x in actual if x.action=="ban" and x.team_id==team_id),None) for side,team_id in team_ids.items()}
        actual_picks={side:next((x.map_name for x in actual if x.action=="pick" and x.team_id==team_id),None) for side,team_id in team_ids.items()}
        opening_top1=sum(int(bool(actual_opening[side] and calculated["opening_bans"][side][0]["map"]==actual_opening[side])) for side in team_ids)/2
        opening_top2=sum(int(bool(actual_opening[side] and actual_opening[side] in {x["map"] for x in calculated["opening_bans"][side][:2]})) for side in team_ids)/2
        pick_top1=sum(int(bool(actual_picks[side] and max(calculated["maps"],key=lambda x:x[f"pick_by_{side}_probability"])["map"]==actual_picks[side])) for side in team_ids)/2
        actual_decider=next((x.map_name for x in actual if x.action=="decider"),None)
        decider_top1=float(bool(actual_decider and max(calculated["maps"],key=lambda x:x["decider_probability"])["map"]==actual_decider))
        return {"match_id":match_id,"model_version":CALCULATED_VETO_MODEL_VERSION,"as_of":match.match_date,"map_pool_version":match.map_pool_version,"maps":rows,"top_3_hit_count":hits,"top_3_accuracy":round(hits/3,6),"opening_ban_top1_accuracy":opening_top1,"opening_ban_top2_accuracy":opening_top2,"pick_top1_accuracy":pick_top1,"decider_top1_accuracy":decider_top1,"brier_score":brier,"log_loss":loss,"baseline_probability":baseline,"baseline_brier":base_brier,"baseline_log_loss":base_loss}

    async def backtest_summary(self)->dict:
        from cs2eye.models.match import Match
        matches=list((await self.session.execute(select(Match).where(Match.format=="bo3",Match.veto_data_status=="complete",Match.team_a_id.is_not(None),Match.team_b_id.is_not(None),Match.map_pool_version.is_not(None)).order_by(Match.match_date,Match.id))).scalars())
        results=[]
        for match in matches:
            try:
                result=await self.backtest(match.id)
            except ValueError:
                continue
            # A minimally informative prior for both teams is required.
            if all(item["confidence"]==0 for item in result["maps"]):continue
            results.append(result)
        n=len(results);maps=sum(len(x["maps"]) for x in results)
        mean=lambda key:round(sum(x[key] for x in results)/n,6) if n else None
        return {"model_version":CALCULATED_VETO_MODEL_VERSION,"series_evaluated":n,"maps_evaluated":maps,"avg_top3_hits":mean("top_3_hit_count"),"top3_accuracy":mean("top_3_accuracy"),"opening_ban_top1_accuracy":mean("opening_ban_top1_accuracy"),"opening_ban_top2_accuracy":mean("opening_ban_top2_accuracy"),"pick_top1_accuracy":mean("pick_top1_accuracy"),"decider_top1_accuracy":mean("decider_top1_accuracy"),"brier_score":mean("brier_score"),"log_loss":mean("log_loss"),"baseline_brier":mean("baseline_brier"),"baseline_log_loss":mean("baseline_log_loss")}
