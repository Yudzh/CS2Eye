from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.matchup_config import MATCHUP_WEIGHTS, TACTICAL_WEIGHTS
from cs2eye.analytics.scoring.core import FactorInput, regress_rate, score_factors
from cs2eye.analytics.win_probability_config import MIN_HISTORICAL_MAPS_PER_TEAM, WIN_PROBABILITY_FEATURES
from cs2eye.models.demo import (DemoMapResult,DemoPlayerStat,DemoTeamBombStat,DemoTeamCombatStat,
    DemoTeamEconomyStat,DemoTeamRoster,DemoTeamSideStat,DemoTeamUtilityStat)
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match,MatchVetoAction
from cs2eye.models.team import Team,TeamRankingSnapshot,TeamRosterMember
from cs2eye.services.matchup_service import advantage_level,confidence_level
from cs2eye.services.player_service import calculate_player_strength
from cs2eye.services.team_strength_service import TeamPerformanceInput,calculate_team_strength
from cs2eye.services.form_context_service import FormContextService

def clamp(x:float)->float:return max(0,min(100,x))
def rate(n:int,d:int)->float|None:return n/d*100 if d else None
def mean(xs):
    values=[float(x) for x in xs if x is not None]
    return sum(values)/len(values) if values else None
def cross(a,b):return clamp(50+(a-b)/2) if a is not None and b is not None else None
def nested(data:dict|None,*keys):
    value:Any=data
    for key in keys:
        if not isinstance(value,dict):return None
        value=value.get(key)
    return float(value) if value is not None else None

@dataclass
class HistoricalMap:
    demo_id:int;match_id:int;match_date:date;team_id:int;opponent_id:int;map_name:str;won:bool
    rounds_won:int;rounds_lost:int;roster_id:int|None;opponent_rank_group:str="unknown"
    ct_won:int=0;ct_played:int=0;t_won:int=0;t_played:int=0
    bomb:Any=None;economy:Any=None;combat:Any=None;utility:Any=None

@dataclass
class HistoricalState:
    maps:dict[int,list[HistoricalMap]]=field(default_factory=lambda:defaultdict(list))
    roster_id:dict[int,int]=field(default_factory=dict)
    player_stats:dict[int,list[DemoPlayerStat]]=field(default_factory=lambda:defaultdict(list))
    veto:dict[int,list[MatchVetoAction]]=field(default_factory=lambda:defaultdict(list))
    h2h:dict[frozenset[int],list[tuple[int,int]]]=field(default_factory=lambda:defaultdict(list))

@dataclass(frozen=True)
class HistoricalExample:
    series_id:int;match_date:date;team_a_id:int;team_b_id:int;target:int;features:dict[str,float]
    matchup:dict;confidence:float

class AnalyticsAsOfService:
    """Bulk-loaded rolling context. A series updates state only after its feature row is built."""
    def __init__(self,session:AsyncSession):self.session=session

    async def build_dataset(self,analysis_mode:str="pre_veto")->tuple[list[HistoricalExample],dict]:
        data=await self._preload();state=HistoricalState();examples=[];excluded=defaultdict(int)
        rankings=self._ranking_index(data["rankings"]);members=defaultdict(list)
        for member in data["members"]:
            if member.player_id is not None:members[member.roster_id].append(member.player_id)
        maps_by_match=defaultdict(list)
        for item in data["maps"]:maps_by_match[item.match_id].append(item)
        self._annotate_opponent_ranks(data["maps"],rankings)
        veto_by_match=defaultdict(list)
        for action in data["veto"]:veto_by_match[action.match_series_id].append(action)
        stats_by_demo=defaultdict(list)
        for stat in data["player_stats"]:stats_by_demo[stat.demo_file_id].append(stat)
        total=0;by_date=defaultdict(list)
        for match in data["matches"]:by_date[match.match_date].append(match)
        for day in sorted(by_date):
            # Match has date granularity, not start_time. All matches on the same
            # date see the state from before that date; only then is the day added.
            for match in by_date[day]:
                total+=1;maps=maps_by_match[match.id];reason=self._eligibility(match,maps,state)
                if reason:excluded[reason]+=1
                else:
                    context=self._matchup(match,state,rankings,members,veto_by_match[match.id] if analysis_mode=="post_veto" else None)
                    if context["reliability"]<.15:excluded["insufficient_reliability"]+=1
                    else:
                        context["form_context"]=await FormContextService(self.session).compare(
                            match.team_a_id,match.team_b_id,match.match_date,match.tournament_id,match.id)
                        features=self.features(context,match.format,rankings,match.match_date,match.team_a_id,match.team_b_id)
                        examples.append(HistoricalExample(match.id,match.match_date,match.team_a_id,match.team_b_id,int(match.winner_team_id==match.team_a_id),features,context,context["reliability"]))
            for match in by_date[day]:self._update(match,maps_by_match[match.id],veto_by_match[match.id],stats_by_demo,state)
        positives=sum(item.target for item in examples)
        return examples,{"total_series":total,"eligible":len(examples),"excluded":total-len(examples),"coverage":len(examples)/total if total else 0,"excluded_reasons":dict(excluded),"target_distribution":{"team_a_wins":positives,"team_b_wins":len(examples)-positives},"date_range":{"first":examples[0].match_date.isoformat() if examples else None,"last":examples[-1].match_date.isoformat() if examples else None},"bulk_queries":13,"analysis_mode":analysis_mode,"cutoff_policy":"strictly_before_match_date; same-day series are added after all predictions for that date"}

    async def calculate(self,a:int,b:int,as_of:date,format:str="bo3",analysis_mode:str="pre_veto",series_id:int|None=None)->dict:
        data=await self._preload();state=HistoricalState();rankings=self._ranking_index(data["rankings"]);members=defaultdict(list)
        team_names={team.id:team.name for team in data["teams"]}
        for member in data["members"]:
            if member.player_id is not None:members[member.roster_id].append(member.player_id)
        maps_by_match=defaultdict(list);veto_by_match=defaultdict(list);stats_by_demo=defaultdict(list)
        for item in data["maps"]:maps_by_match[item.match_id].append(item)
        self._annotate_opponent_ranks(data["maps"],rankings)
        for action in data["veto"]:veto_by_match[action.match_series_id].append(action)
        for stat in data["player_stats"]:stats_by_demo[stat.demo_file_id].append(stat)
        target=None
        for match in data["matches"]:
            if match.match_date>=as_of:break
            self._update(match,maps_by_match[match.id],veto_by_match[match.id],stats_by_demo,state)
        if series_id:target=next((m for m in data["matches"] if m.id==series_id),None)
        pseudo=target or SimpleNamespace(id=series_id or 0,match_date=as_of,team_a_id=a,team_b_id=b,format=format,winner_team_id=None)
        if len(state.maps[a])<MIN_HISTORICAL_MAPS_PER_TEAM or len(state.maps[b])<MIN_HISTORICAL_MAPS_PER_TEAM:return self._unavailable(a,b,as_of,format,analysis_mode,"insufficient_history")
        actual=veto_by_match.get(series_id,[]) if analysis_mode=="post_veto" and series_id else None
        context=self._matchup(pseudo,state,rankings,members,actual)
        context["form_context"]=await FormContextService(self.session).compare(
            a,b,as_of,getattr(target,"tournament_id",None),series_id)
        context["team_a"]["name"]=team_names.get(a,str(a))
        context["team_b"]["name"]=team_names.get(b,str(b))
        winner=context["advantage"].get("team_id")
        context["advantage"]["team_name"]=team_names.get(winner) if winner else None
        context.update({"as_of":as_of,"analysis_mode":analysis_mode,"format":format,"historical_policy":"strict_rolling_before_date"})
        context["prediction_features"]=self.features(context,format,rankings,as_of,a,b)
        return context

    def _eligibility(self,match,maps,state):
        if not match.team_a_id or not match.team_b_id:return "missing_teams"
        if match.winner_team_id not in {match.team_a_id,match.team_b_id}:return "missing_result"
        if match.format not in {"bo1","bo3","bo5"}:return "unknown_format"
        if not maps:return "missing_demo_maps"
        if len(state.maps[match.team_a_id])<MIN_HISTORICAL_MAPS_PER_TEAM or len(state.maps[match.team_b_id])<MIN_HISTORICAL_MAPS_PER_TEAM:return "insufficient_history"
        if match.team_a_id not in state.roster_id or match.team_b_id not in state.roster_id:return "missing_historical_roster"
        return None

    @staticmethod
    def features(context,format,rankings,as_of,a,b):
        factors={x["key"]:x for x in context["factors"]};strength=(factors.get("team_strength") or {}).get("score") or 50
        rank_a=AnalyticsAsOfService._rank(rankings,a,as_of);rank_b=AnalyticsAsOfService._rank(rankings,b,as_of);rank_adv=0 if not rank_a or not rank_b else max(-30,min(30,rank_b-rank_a))/30
        strength_delta=(strength-50)/50
        form=context.get("form_context",{});fa=form.get("team_a_form_context",{});fb=form.get("team_b_form_context",{})
        def delta(key):return 0 if fa.get(key) is None or fb.get(key) is None else (float(fa[key])-float(fb[key]))/100
        values={"matchup_score_centered":(context["team_a"]["score"]-50)/50,"raw_matchup_centered":(context["raw_score"]-50)/50,"matchup_reliability_advantage":(context["team_a"]["score"]-50)/50*context["reliability"],"team_strength_difference":strength_delta,"map_pool_advantage":(((factors.get("map_veto") or {}).get("score") or 50)-50)/50,"current_roster_advantage":(((factors.get("current_roster_form") or {}).get("score") or 50)-50)/50,"tactical_advantage":(((factors.get("tactical_matchup") or {}).get("score") or 50)-50)/50,"h2h_advantage":(((factors.get("h2h") or {}).get("score") or 50)-50)/50,"leadership_advantage":0,"ranking_advantage":rank_adv,"format_bo1_strength":strength_delta if format=="bo1" else 0,"format_bo3_strength":strength_delta if format=="bo3" else 0,"format_bo5_strength":strength_delta if format=="bo5" else 0,"tournament_form_advantage":delta("tournament_form_score"),"recent_60d_adjusted_form_advantage":delta("recent_60d_adjusted_form_score"),"strength_of_schedule_advantage":delta("strength_of_schedule_score"),"performance_vs_expectation_advantage":delta("performance_vs_expectation_score")}
        return {key:float(values[key]) for key in WIN_PROBABILITY_FEATURES}

    def _matchup(self,match,state,rankings,members,actual_veto):
        a,b=match.team_a_id,match.team_b_id;sa,ca=self._team_strength(a,state,members,match.match_date);sb,cb=self._team_strength(b,state,members,match.match_date)
        map_score,map_rows,map_conf=self._map_veto(a,b,state,match.format,actual_veto)
        roster=self._roster_form(a,b,state);tactical,tactical_detail=self._tactical(a,b,state)
        h2h=self._h2h(a,b,state);hcount=len(state.h2h[frozenset((a,b))])
        inputs=[FactorInput("map_veto","Карты и вето",None,map_score,.35,len(map_rows),map_conf,"Исторические карты/veto строго до as_of."),FactorInput("team_strength","Сила команд",None,cross(sa,sb),.25,confidence=min(ca,cb),reason="Team Strength V2 из historical Player Strength и результатов до as_of."),FactorInput("current_roster_form","Состав и форма",None,roster,.15,confidence=min(1,min(len(state.maps[a]),len(state.maps[b]))/10),reason="Последние карты roster_as_of."),FactorInput("tactical_matchup","Тактика",tactical_detail,tactical,.10,confidence=tactical_detail["coverage"],reason="CT/T, bomb, economy, combat, utility до as_of."),FactorInput("h2h","Личные встречи",None,h2h,.10,hcount,min(1,hcount/5),"Только предыдущие серии.",h2h is not None),FactorInput("leadership_context","Лидерство",None,None,.05,available=False,reason="Исторические роли IGL/Coach недостаточно надёжны.")]
        available=[x for x in inputs if x.available and x.normalized_score is not None];reliability=sum((x.confidence or 0)*x.weight for x in available)/sum(x.weight for x in available) if available else 0;result=score_factors(inputs,reliability);score=result.final_score
        return {"model_version":"matchup_v1","score_semantics":"analytical_score_0_100_not_probability","team_a":{"id":a,"score":score,"advantage":round(score-50,2)},"team_b":{"id":b,"score":round(100-score,2),"advantage":round(50-score,2)},"raw_score":result.raw_score,"reliability":result.reliability,"confidence_level":confidence_level(result.reliability),"advantage":{"team_id":a if score>53 else b if score<47 else None,"level":advantage_level(score)},"factors":[{**x.__dict__,"score":x.normalized_score,"sample":x.sample_size} for x in result.factors],"maps":map_rows,"tactical":tactical_detail,"veto":{"basis":"actual_veto" if actual_veto else "historical_calculated_veto","series_id":getattr(match,"id",None)},"roster_as_of":{"team_a":state.roster_id.get(a),"team_b":state.roster_id.get(b)},"ranking_as_of":{"team_a":self._rank(rankings,a,match.match_date),"team_b":self._rank(rankings,b,match.match_date)},"strict_historical":True,"limitations":["Round Swing excluded from strict historical features: active v1 artifact was trained using future matches relative to historical rows.","Historical Leadership excluded: role tenure snapshots are not reliable.","Match Series stores a date but no exact start time; same-day matches are conservatively hidden from one another."]}

    def _team_strength(self,team_id,state,members,as_of):
        maps=state.maps[team_id];roster=state.roster_id.get(team_id);player_scores=[]
        for player_id in members.get(roster,[]):
            rows=state.player_stats[player_id]
            if not rows:continue
            rounds=sum(x.rounds_played for x in rows);rating=sum(x.internal_rating*x.rounds_played for x in rows)/rounds
            recent=rows[-10:];rr=sum(x.rounds_played for x in recent);recent_rating=sum(x.internal_rating*x.rounds_played for x in recent)/rr if rr else None
            top15=[x for x in rows if x.opponent_rank_group=="top_15"];t15r=sum(x.rounds_played for x in top15);top30=[x for x in rows if x.opponent_rank_group=="top_16_30"];t30r=sum(x.rounds_played for x in top30)
            score,_=calculate_player_strength(None,internal_rating=rating,internal_maps=len(rows),top15_rating=sum(x.internal_rating*x.rounds_played for x in top15)/t15r if t15r else None,top15_maps=len(top15),top16_30_rating=sum(x.internal_rating*x.rounds_played for x in top30)/t30r if t30r else None,top16_30_maps=len(top30),recent_rating=recent_rating,recent_maps=len(recent))
            if score is not None:player_scores.append(score)
        def performance(selected):
            if not selected:return None
            mr,_=regress_rate(sum(x.won for x in selected),len(selected),prior_size=8);rw=sum(x.rounds_won for x in selected);rt=sum(x.rounds_won+x.rounds_lost for x in selected);rr,_=regress_rate(rw,rt,prior_size=24);return (mr*.6+rr*.4)*100
        recent=maps[-10:];p=TeamPerformanceInput(performance(maps),len(maps),performance([x for x in maps if x.opponent_rank_group=="top_15"]),sum(x.opponent_rank_group=="top_15" for x in maps),performance([x for x in maps if x.opponent_rank_group=="top_16_30"]),sum(x.opponent_rank_group=="top_16_30" for x in maps),performance(recent),len(recent),performance(maps[-5:]),min(5,len(maps)),sum(x.roster_id==roster for x in maps))
        fake=[(SimpleNamespace(player_strength=value),SimpleNamespace(participant_type="player",is_active=True,left_at=None,joined_at=None,role=None)) for value in player_scores]
        result=calculate_team_strength(fake,performance=p);return result.final_score,result.reliability

    def _map_veto(self,a,b,state,format,actual):
        names=sorted({x.map_name for x in state.maps[a]+state.maps[b]});rows=[]
        for name in names:
            aa=[x for x in state.maps[a] if x.map_name==name];bb=[x for x in state.maps[b] if x.map_name==name]
            if not aa or not bb:continue
            ar,_=regress_rate(sum(x.won for x in aa),len(aa),prior_size=5);br,_=regress_rate(sum(x.won for x in bb),len(bb),prior_size=5);score=clamp(50+(ar-br)*50);rows.append({"map":name,"score":score,"sample":min(len(aa),len(bb))})
        actual_roles={x.map_name:x.action for x in actual or []};veto_a=state.veto[a];veto_b=state.veto[b]
        for row in rows:
            bans=sum(x.action=="ban" and x.map_name==row["map"] for x in veto_a+veto_b);total=max(1,len(veto_a)+len(veto_b));row["playability"]=.02 if actual_roles.get(row["map"])=="ban" else 1 if actual_roles.get(row["map"]) in {"pick","decider"} else max(.05,1-bans/total);row["role"]=actual_roles.get(row["map"],"calculated")
        count={"bo1":1,"bo3":3,"bo5":5}.get(format,3);chosen=sorted(rows,key=lambda x:(x["role"] in {"pick","decider"},x["playability"]),reverse=True)[:count];total=sum(x["playability"] for x in chosen)
        for row in chosen:row["playability_weight"]=row["playability"]/total if total else 0;row["contribution"]=(row["score"]-50)*row["playability_weight"]
        score=50+sum(x["contribution"] for x in chosen) if chosen else None;conf=min(1,sum(x["sample"] for x in chosen)/15) if chosen else 0
        return score,chosen,conf

    def _roster_form(self,a,b,state):
        def value(team):
            roster=state.roster_id.get(team);rows=[x for x in state.maps[team] if x.roster_id==roster][-10:]
            if not rows:return None
            observed=sum(x.won for x in rows)/len(rows);rel=len(rows)/(len(rows)+5);return 50+(observed*100-50)*rel
        return cross(value(a),value(b))

    def _tactical(self,a,b,state):
        def team(team):
            rows=state.maps[team][-20:];ct=rate(sum(x.ct_won for x in rows),sum(x.ct_played for x in rows));t=rate(sum(x.t_won for x in rows),sum(x.t_played for x in rows));post=mean([getattr(x.bomb,"postplant_win_rate",None) for x in rows]);retake=mean([getattr(x.bomb,"retake_win_rate",None) for x in rows]);full=mean([rate(getattr(x.economy,"full_buy_vs_full_buy_wins",0),getattr(x.economy,"full_buy_vs_full_buy_rounds",0)) for x in rows]);combat=mean([nested(getattr(x.combat,"combat_data",None),"opening","success_rate") for x in rows]);utility=mean([nested(getattr(x.utility,"utility_data",None),"utility_damage_per_round") for x in rows]);trade=mean([nested(getattr(x.combat,"combat_data",None),"trade","trade_rate") for x in rows]);return {"ct":ct,"t":t,"post":post,"retake":retake,"economy":full,"combat":combat,"utility":utility,"trade":trade}
        x,y=team(a),team(b);components={"side":mean([cross(x["t"],y["ct"]),cross(x["ct"],y["t"])]),"bomb":mean([cross(x["post"],y["retake"]),cross(x["retake"],y["post"])]),"combat_swing":cross(x["combat"],y["combat"]),"economy":cross(x["economy"],y["economy"]),"utility":cross(x["utility"],y["utility"]),"trading":cross(x["trade"],y["trade"])};available=[(components[k],w) for k,w in TACTICAL_WEIGHTS.items() if components[k] is not None];total=sum(w for _,w in available);score=sum(v*w for v,w in available)/total if total else None;return score,{**components,"score":score,"coverage":total}

    @staticmethod
    def _h2h(a,b,state):
        rows=state.h2h[frozenset((a,b))]
        if not rows:return None
        wins=sum(winner==a for _,winner in rows);rel=len(rows)/(len(rows)+4);return 50+(wins/len(rows)*100-50)*rel

    def _update(self,match,maps,veto,stats_by_demo,state):
        if match.team_a_id and match.team_b_id and match.winner_team_id in {match.team_a_id,match.team_b_id}:state.h2h[frozenset((match.team_a_id,match.team_b_id))].append((match.id,match.winner_team_id))
        for item in maps:
            state.maps[item.team_id].append(item)
            if item.roster_id:state.roster_id[item.team_id]=item.roster_id
            for stat in stats_by_demo[item.demo_id]:
                if stat.player_id is not None and stat.demo_team_id==item.team_id:state.player_stats[stat.player_id].append(stat)
        for action in veto:
            if action.team_id:state.veto[action.team_id].append(action)

    @staticmethod
    def _ranking_index(rows):
        out=defaultdict(list)
        for row in rows:out[row.team_id].append(row)
        return out
    @staticmethod
    def _annotate_opponent_ranks(maps,index):
        for item in maps:
            rank=AnalyticsAsOfService._rank(index,item.opponent_id,item.match_date)
            item.opponent_rank_group="top_15" if rank and rank<=15 else "top_16_30" if rank and rank<=30 else "unknown"
    @staticmethod
    def _rank(index,team_id,as_of):
        row=next((x for x in reversed(index.get(team_id,[])) if x.ranking_date<=as_of),None);return row.rank if row else None
    @staticmethod
    def _unavailable(a,b,as_of,format,mode,reason):return {"model_version":"matchup_v1","team_a":{"id":a,"score":50},"team_b":{"id":b,"score":50},"raw_score":50,"reliability":0,"confidence_level":"low","factors":[],"maps":[],"tactical":{"score":None},"as_of":as_of,"format":format,"analysis_mode":mode,"historical_policy":"strict_rolling_before_date","status":"insufficient_data","limitations":[reason]}

    async def _preload(self):
        matches=list((await self.session.execute(select(Match).where(Match.status=="completed").order_by(Match.match_date,Match.id))).scalars())
        joined=(await self.session.execute(select(DemoFile,DemoMapResult).join(DemoMapResult,DemoMapResult.demo_file_id==DemoFile.id).where(DemoFile.match_id.is_not(None),DemoMapResult.round_data_status=="complete").order_by(DemoFile.match_date,DemoFile.id))).all();demo_ids=[d.id for d,_ in joined]
        async def rows(model):return list((await self.session.execute(select(model).where(model.demo_file_id.in_(demo_ids)))).scalars()) if demo_ids else []
        rosters=await rows(DemoTeamRoster);roster_by={(x.demo_file_id,x.team_id):x for x in rosters};sides=await rows(DemoTeamSideStat);side_by={(x.demo_file_id,x.team_id):x for x in sides};bombs=await rows(DemoTeamBombStat);bomb_by={(x.demo_file_id,x.team_id):x for x in bombs};economies=await rows(DemoTeamEconomyStat);economy_by={(x.demo_file_id,x.team_id):x for x in economies};combats=await rows(DemoTeamCombatStat);combat_by={(x.demo_file_id,x.team_id):x for x in combats};utilities=await rows(DemoTeamUtilityStat);utility_by={(x.demo_file_id,x.team_id):x for x in utilities}
        maps=[]
        for demo,result in joined:
            if not result.map_name or not result.team_a_id or not result.team_b_id or result.team_a_score is None or result.team_b_score is None:continue
            for team,opp,won,rw,rl in ((result.team_a_id,result.team_b_id,result.team_a_score>result.team_b_score,result.team_a_score,result.team_b_score),(result.team_b_id,result.team_a_id,result.team_b_score>result.team_a_score,result.team_b_score,result.team_a_score)):
                side=side_by.get((demo.id,team));link=roster_by.get((demo.id,team));maps.append(HistoricalMap(demo.id,demo.match_id,demo.match_date,team,opp,result.map_name,won,rw,rl,link.roster_id if link and link.resolution_status=="complete" else None,"unknown",getattr(side,"ct_rounds_won",0),getattr(side,"ct_rounds_played",0),getattr(side,"t_rounds_won",0),getattr(side,"t_rounds_played",0),bomb_by.get((demo.id,team)),economy_by.get((demo.id,team)),combat_by.get((demo.id,team)),utility_by.get((demo.id,team))))
        return {"matches":matches,"maps":maps,"player_stats":await rows(DemoPlayerStat),"rankings":list((await self.session.execute(select(TeamRankingSnapshot).order_by(TeamRankingSnapshot.ranking_date,TeamRankingSnapshot.id))).scalars()),"veto":list((await self.session.execute(select(MatchVetoAction).order_by(MatchVetoAction.match_series_id,MatchVetoAction.order_index))).scalars()),"members":list((await self.session.execute(select(TeamRosterMember))).scalars()),"teams":list((await self.session.execute(select(Team))).scalars()),"_query_note":"13 bounded bulk queries"}
