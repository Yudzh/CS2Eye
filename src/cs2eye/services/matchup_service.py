from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.matchup_config import ACTIVE_MATCHUP_CONFIG, MATCHUP_CONFIGS, MATCHUP_MODEL_VERSION, MATCHUP_WEIGHTS, TACTICAL_WEIGHTS
from cs2eye.analytics.matchup_engine import apply_config_to_payload, calculate_matchup
from cs2eye.analytics.scoring.core import FactorInput, score_factors
from cs2eye.models.match import Match, MatchVetoAction
from cs2eye.services.calculated_veto_service import CalculatedVetoService
from cs2eye.services.leadership_service import LeadershipService
from cs2eye.services.team_comparison_service import TeamComparisonService
from cs2eye.services.team_h2h_service import TeamH2HService
from cs2eye.services.form_context_service import FormContextService


def clamp(value: float) -> float: return max(0.0, min(100.0, value))
def mean(values: list[float | None]) -> float | None:
    present=[value for value in values if value is not None]
    return sum(present)/len(present) if present else None
def cross(a: float | None, b: float | None) -> float | None:
    return clamp(50+(a-b)/2) if a is not None and b is not None else None


def advantage_level(score: float) -> str:
    distance=abs(score-50)
    if distance < 3:return "neutral"
    if distance < 10:return "slight"
    if distance < 20:return "moderate"
    return "strong"


def confidence_level(reliability: float) -> str:
    return "low" if reliability < .45 else "medium" if reliability < .75 else "high"

def form_context_input(form_pair:dict)->FactorInput:
    form_a,form_b=form_pair["team_a_form_context"],form_pair["team_b_form_context"]
    def value(payload):
        present=[float(payload[key]) for key in ("tournament_form_score","recent_60d_adjusted_form_score","strength_of_schedule_score","performance_vs_expectation_score") if payload.get(key) is not None]
        return sum(present)/len(present) if present else None
    score=cross(value(form_a),value(form_b));confidence=min(float(form_a.get("recent_60d_reliability",0)),float(form_b.get("recent_60d_reliability",0)))
    return FactorInput("form_context","Контекст формы",form_pair,score,MATCHUP_WEIGHTS["form_context"],min(form_a["recent_60d_matches_count"],form_b["recent_60d_matches_count"]),confidence,"Турнирная форма и последние 60 дней с поправкой на силу соперников и ожидание.",score is not None)


def relevant_map_weights(calculated: dict, format: str, actual: list[MatchVetoAction] | None = None) -> dict[str, tuple[float,str]]:
    maps={item["map"]:item for item in calculated["maps"]}
    raw:dict[str,tuple[float,str]]={}
    if actual:
        for action in actual:
            role="team_a_pick" if action.action=="pick" and action.team_id==calculated["team_a"]["id"] else "team_b_pick" if action.action=="pick" else "decider" if action.action=="decider" else "ban"
            raw[action.map_name]=(.02 if role=="ban" else 1.0,role)
    elif format=="bo3":
        for item in calculated["maps"]:
            raw[item["map"]]=(item["series_map_probability"],"probability")
    else:
        playable=sorted(((name,max(1.0,100-(item["team_a"]["calculated_ban_score"]+item["team_b"]["calculated_ban_score"])/2)) for name,item in maps.items()),key=lambda pair:pair[1],reverse=True)
        count=1 if format=="bo1" else min(5,len(playable))
        for index,(name,value) in enumerate(playable):raw[name]=((value**2 if index<count else value*.01),"remaining" if format=="bo1" else "played" if index<count else "ban")
    total=sum(value for name,(value,_) in raw.items() if name in maps)
    return {name:(value/total,role) for name,(value,role) in raw.items() if name in maps and total}


def aggregate_maps(calculated: dict, weights: dict[str,tuple[float,str]]) -> tuple[float|None,list[dict],dict]:
    indexed={item["map"]:item for item in calculated["maps"]};breakdown=[]
    for name,(weight,role) in weights.items():
        item=indexed[name];score=(item["team_a"]["matchup_map_score"]+100-item["team_b"]["matchup_map_score"])/2
        confidence=min(item["team_a"]["matchup_confidence"],item["team_b"]["matchup_confidence"])
        breakdown.append({"map":name,"map_matchup_score":score,"team_b_score":round(100-score,2),"playability_weight":round(weight,6),"role":role,"confidence":round(confidence,4),"contribution":round((score-50)*weight,2)})
    map_score=50+sum(item["contribution"] for item in breakdown) if breakdown else None
    tactical={}
    for key,configured in TACTICAL_WEIGHTS.items():
        values=[]
        for row in breakdown:
            pair=indexed[row["map"]];component_a=pair["team_a"].get("tactical_components",{}).get(key);component_b=pair["team_b"].get("tactical_components",{}).get(key)
            component=(component_a+100-component_b)/2 if component_a is not None and component_b is not None else component_a if component_a is not None else 100-component_b if component_b is not None else None
            if component is not None:values.append((component,row["playability_weight"]))
        total=sum(weight for _,weight in values)
        tactical[key]={"score":round(sum(value*weight for value,weight in values)/total,2),"weight":configured,"available":True} if total else {"score":None,"weight":configured,"available":False}
    available=sum(item["weight"] for item in tactical.values() if item["available"])
    tactical_score=50+sum((item["score"]-50)*item["weight"]/available for item in tactical.values() if item["available"]) if available else None
    tactical["score"]=round(tactical_score,2) if tactical_score is not None else None
    return (round(map_score,2) if map_score is not None else None),breakdown,tactical


class MatchupService:
    def __init__(self,session:AsyncSession):self.session=session

    async def calculate(self,team_a_id:int,team_b_id:int,format:str="bo3",analysis_mode:str="pre_veto",as_of:date|None=None,series_id:int|None=None,model_version:str|None=None)->dict:
        if format not in {"bo1","bo3","bo5"}:raise ValueError("format must be bo1, bo3 or bo5")
        if analysis_mode not in {"pre_veto","post_veto"}:raise ValueError("analysis_mode must be pre_veto or post_veto")
        if team_a_id==team_b_id:raise ValueError("Нужны две разные команды.")
        config=MATCHUP_CONFIGS.get(model_version or ACTIVE_MATCHUP_CONFIG.version)
        if config is None:raise ValueError("Unknown Matchup model version.")
        as_of=as_of or date.today();historical=as_of < date.today()
        # Current aggregate/roster artifacts are not temporal snapshots. In a historical
        # request they are deliberately disabled instead of leaking future information.
        if historical:
            from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
            payload=await AnalyticsAsOfService(self.session).calculate(team_a_id,team_b_id,as_of,format,analysis_mode,series_id)
            return payload if config.version==MATCHUP_MODEL_VERSION else apply_config_to_payload(payload,config)
        comparison=await TeamComparisonService(self.session,now=datetime.combine(as_of,datetime.min.time(),tzinfo=UTC)).compare(team_a_id,team_b_id)
        calculated=await CalculatedVetoService(self.session,today=as_of).calculate(team_a_id,team_b_id,"bo3")
        actual=await self._actual_veto(team_a_id,team_b_id,series_id,as_of) if analysis_mode=="post_veto" else None
        if analysis_mode=="post_veto" and not actual:raise ValueError("Для post_veto нужен series_id с фактическим вето.")
        weights=relevant_map_weights(calculated,format,actual);map_score,maps,tactical=aggregate_maps(calculated,weights)
        sa,sb=comparison.team_a.strength,comparison.team_b.strength
        strength_score=cross(sa.team_strength_score,sb.team_strength_score)
        strength_conf=min(sa.reliability,sb.reliability)
        indexed_maps={item["map"]:item for item in calculated["maps"]};roster_values=[];roster_conf_values=[]
        for name,(weight,_) in weights.items():
            pair=indexed_maps[name];fa=pair["team_a"].get("roster_form",{});fb=pair["team_b"].get("roster_form",{});value=cross(fa.get("recent"),fb.get("recent"))
            if value is not None:roster_values.append((value,weight));roster_conf_values.append((min(fa.get("freshness",0),fb.get("freshness",0))/100*min(1,(fa.get("maps",0)+fb.get("maps",0))/20),weight))
        roster_total=sum(weight for _,weight in roster_values);roster_score=sum(value*weight for value,weight in roster_values)/roster_total if roster_total else None
        roster_conf=sum(value*weight for value,weight in roster_conf_values)/sum(weight for _,weight in roster_conf_values) if roster_conf_values else 0
        h2h=await TeamH2HService(self.session,today=as_of).compare(team_a_id,team_b_id,recent_limit=20)
        hslice=h2h.current_rosters if h2h.current_rosters.maps_played else h2h.organizations
        h2h_score=hslice.team_a.h2h_rating if hslice.maps_played else None;h2h_conf=hslice.confidence_score/100 if hslice.maps_played else 0
        leadership_a,leadership_b=await LeadershipService(self.session).team(team_a_id),await LeadershipService(self.session).team(team_b_id)
        def leadership(payload):
            values=[(payload["igl"]["score"],.6) for _ in [0] if payload["igl"]]+[(payload["coach"]["score"],.4) for _ in [0] if payload["coach"]]
            return sum(value*weight for value,weight in values)/sum(weight for _,weight in values) if values else None
        la,lb=leadership(leadership_a),leadership(leadership_b);leadership_score=cross(la,lb)
        map_conf=sum(row["confidence"]*row["playability_weight"] for row in maps) if maps else 0
        tactical_conf=map_conf*sum(item["weight"] for key,item in tactical.items() if isinstance(item,dict) and item["available"])
        target_match=await self.session.get(Match,series_id) if series_id else None
        form_pair=await FormContextService(self.session).compare(team_a_id,team_b_id,as_of,
            target_match.tournament_id if target_match else None,series_id)
        form_factor=form_context_input(form_pair)
        inputs=[
            FactorInput("map_veto","Карты и вето",{"mode":analysis_mode,"format":format},map_score,MATCHUP_WEIGHTS["map_veto"],len(maps),map_conf,"Релевантные карты определены фактическим или расчётным вето."),
            FactorInput("team_strength","Сила команд",None,strength_score,MATCHUP_WEIGHTS["team_strength"],confidence=strength_conf,reason="Сравнение готовых Team Strength V2 без повторного расчёта."),
            form_factor,
            FactorInput("current_roster_form","Текущий состав и форма",None,roster_score,MATCHUP_WEIGHTS["current_roster_form"],confidence=roster_conf,reason="Recent 5/10/20 текущего состава плавно смешаны с историей организации через roster reliability."),
            FactorInput("tactical_matchup","Тактическое соответствие",tactical,tactical["score"],MATCHUP_WEIGHTS["tactical_matchup"],confidence=tactical_conf,reason="CT/T, bomb, contextual Swing/combat, economy, utility и trading на релевантных картах."),
            FactorInput("h2h","Личные встречи",{"scope":"current_rosters" if h2h.current_rosters.maps_played else "organizations"},h2h_score,MATCHUP_WEIGHTS["h2h"],hslice.maps_played,h2h_conf,"Текущие составы приоритетнее истории организаций.",h2h_score is not None),
            FactorInput("leadership_context","Лидерство",None,leadership_score,MATCHUP_WEIGHTS["leadership_context"],confidence=mean([1 if la is not None else 0,1 if lb is not None else 0]),reason="Небольшое сравнение IGL и тренеров.",available=leadership_score is not None),
        ]
        available=[item for item in inputs if item.available and item.normalized_score is not None]
        reliability=sum((item.confidence or 0)*item.weight for item in available)/sum(item.weight for item in available) if available else 0
        result=calculate_matchup(inputs,reliability,config);score=result.final_score;team_b_score=round(100-score,2)
        winner=team_a_id if score>53 else team_b_id if score<47 else None
        names={team_a_id:comparison.team_a.team.name,team_b_id:comparison.team_b.team.name}
        return {"model_version":config.version,"score_semantics":"analytical_score_0_100_not_probability","analysis_mode":analysis_mode,"format":format,"as_of":as_of,"historical_policy":"current_snapshot" if not historical else "historical_safe",
            "team_a":{"id":team_a_id,"name":names[team_a_id],"score":score,"advantage":round(score-50,2)},"team_b":{"id":team_b_id,"name":names[team_b_id],"score":team_b_score,"advantage":round(team_b_score-50,2)},
            "raw_score":result.raw_score,"reliability":result.reliability,"raw_coverage":getattr(result,"raw_coverage",None),"effective_coverage":getattr(result,"effective_coverage",None),"factor_agreement_score":getattr(result,"factor_agreement_score",None),"confidence_level":confidence_level(result.reliability),
            "advantage":{"team_id":winner,"team_name":names.get(winner),"level":advantage_level(score)},
            "factors":[{**factor.__dict__,"score":factor.normalized_score,"sample":factor.sample_size} for factor in result.factors],"maps":maps,"tactical":tactical,
            "veto":{"basis":"actual_veto" if actual else "calculated_veto","series_id":series_id,"calculated_veto_model_version":calculated["calculated_veto_model_version"]},
            "form_context":form_pair,"limitations":[]}

    async def _actual_veto(self,a:int,b:int,series_id:int|None,as_of:date)->list[MatchVetoAction]:
        if series_id is None:return []
        match=await self.session.get(Match,series_id)
        if not match or {match.team_a_id,match.team_b_id}!={a,b} or match.match_date>as_of:return []
        return list((await self.session.execute(select(MatchVetoAction).where(MatchVetoAction.match_series_id==series_id).order_by(MatchVetoAction.order_index))).scalars())

    async def _historical_safe(self,a:int,b:int,format:str,mode:str,as_of:date,series_id:int|None)->dict:
        # Safe groundwork for Iteration 19: no present-day strength, roster, Swing,
        # leadership or precomputed aggregates are silently reused for the past.
        actual=await self._actual_veto(a,b,series_id,as_of) if mode=="post_veto" else []
        if mode=="post_veto" and not actual:raise ValueError("Фактическое вето недоступно на указанную дату.")
        names=[]
        from cs2eye.models.team import Team
        for team_id in (a,b):
            team=await self.session.get(Team,team_id)
            if not team:raise ValueError("Команда не найдена.")
            names.append(team.name)
        factors=[FactorInput(key,label,None,None,weight,available=False,reason="Нет безопасного temporal snapshot на as_of.") for key,label,weight in [
            ("map_veto","Карты и вето",.35),("team_strength","Сила команд",.25),("current_roster_form","Текущий состав и форма",.15),("tactical_matchup","Тактическое соответствие",.10),("h2h","Личные встречи",.10),("leadership_context","Лидерство",.05)]]
        result=score_factors(factors,0)
        return {"model_version":MATCHUP_MODEL_VERSION,"score_semantics":"analytical_score_0_100_not_probability","analysis_mode":mode,"format":format,"as_of":as_of,"historical_policy":"strict_no_future_snapshots","team_a":{"id":a,"name":names[0],"score":50.0,"advantage":0.0},"team_b":{"id":b,"name":names[1],"score":50.0,"advantage":0.0},"raw_score":50.0,"reliability":0.0,"confidence_level":"low","advantage":{"team_id":None,"team_name":None,"level":"neutral"},"factors":[{**factor.__dict__,"score":factor.normalized_score,"sample":factor.sample_size} for factor in result.factors],"maps":[],"tactical":{"score":None},"veto":{"basis":"actual_veto" if actual else "unavailable","series_id":series_id},"limitations":["Historical temporal snapshots for Strength/Swing/map aggregates are unavailable; unsafe current data was excluded."]}
