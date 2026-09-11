from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoParseRun,DemoPlayerStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.performance_normalization_service import PerformanceNormalizationService
from cs2eye.analytics.performance_v3_config import (
    MECHANICAL_WEIGHTS, PLAYER_STRENGTH_MODEL_VERSION as MODEL_VERSION,
    PLAYER_STRENGTH_WEIGHTS, SUPPORTING_WEIGHTS,
)

def opponent_rank_group_v3(rank:int|None)->str:
    if rank is None:return "unknown"
    if rank<=10:return "top_1_10"
    if rank<=20:return "top_11_20"
    if rank<=30:return "top_21_30"
    return "others"

def _metric(row:DemoPlayerStat,key:str):
    rounds=int(row.rounds_played or 0);utility=row.utility_data or {};combat=row.combat_data or {}
    values={
        "kills_per_round":row.kills/rounds if rounds else None,
        "adr":float(row.total_damage)/rounds if rounds else None,
        "survival_rate":max(0.,(rounds-row.deaths)/rounds) if rounds else None,
        "flash_assists_per_round":utility.get("flash_assists",0)/rounds if rounds and row.utility_data is not None else None,
        "enemies_flashed_per_flash":utility.get("enemies_flashed_per_flash"),
        "enemy_flash_seconds_per_flash":utility.get("enemy_flash_seconds_per_flash"),
        "utility_damage_per_round":utility.get("utility_damage_per_round"),
        "trade_success_rate":combat.get("trade_success_rate"),
        "teammates_flashed_per_flash":utility.get("teammates_flashed_per_flash"),
    }
    return None if values[key] is None else float(values[key])

def _aggregate(rows:list[DemoPlayerStat])->dict:
    rounds=sum(int(x.rounds_played or 0) for x in rows);maps=len(rows)
    result={"maps":maps,"rounds":rounds,"combat_maps":sum(x.combat_data is not None for x in rows),"utility_maps":sum(x.utility_data is not None for x in rows)}
    for key in MECHANICAL_WEIGHTS:
        pairs=[(_metric(row,key),int(row.rounds_played or 0)) for row in rows]
        pairs=[(value,weight) for value,weight in pairs if value is not None and weight]
        result[key]=sum(value*weight for value,weight in pairs)/sum(weight for _,weight in pairs) if pairs else None
    utility=[row.utility_data for row in rows if row.utility_data is not None]
    combat=[row.combat_data for row in rows if row.combat_data is not None]
    def total(values,key):return sum(float(x.get(key,0) or 0) for x in values)
    utility_rounds=sum(int(row.rounds_played or 0) for row in rows if row.utility_data is not None)
    flashes=total(utility,"flash_thrown")
    result["flash_assists_per_round"]=total(utility,"flash_assists")/utility_rounds if utility_rounds else None
    result["enemies_flashed_per_flash"]=total(utility,"enemies_flashed")/flashes if flashes else None
    result["enemy_flash_seconds_per_flash"]=total(utility,"enemy_flash_duration")/flashes if flashes else None
    result["utility_damage_per_round"]=total(utility,"utility_damage")/utility_rounds if utility_rounds else None
    result["teammates_flashed_per_flash"]=total(utility,"teammates_flashed")/flashes if flashes else None
    trade_opportunities=total(combat,"trade_opportunities")
    result["trade_success_rate"]=total(combat,"trade_kills")/trade_opportunities if trade_opportunities else None
    return result

def _normalize(value:float|None,reference:list[float],inverse:bool=False)->float|None:
    return PerformanceNormalizationService.score(value,reference,inverse=inverse)

def _block(metrics:dict,weights:dict[str,float],references:dict[str,list[float]],*,inverse:set[str]=set(),reliability:float)->dict:
    factors=[]
    for key,weight in weights.items():
        raw=metrics.get(key);score=_normalize(raw,references.get(key,[]),key in inverse)
        factors.append({"key":key,"raw_value":None if raw is None else round(raw,6),"normalized_score":None if score is None else round(score,2),"weight":weight,"effective_weight":0.,"sample":{"maps":metrics["maps"],"rounds":metrics["rounds"]},"reliability":round(reliability,4),"available":score is not None,"normalization":PerformanceNormalizationService.VERSION})
    total=sum(item["weight"] for item in factors if item["available"])
    for item in factors:
        item["effective_weight"]=round(item["weight"]/total,6) if item["available"] and total else 0.
    score=sum(item["normalized_score"]*item["effective_weight"] for item in factors if item["available"]) if total else None
    return {"score":None if score is None else round(score,2),"reliability":round(reliability,4),"factors":factors}

class PlayerStrengthV3Service:
    def __init__(self,session:AsyncSession):
        self.session=session
        self._datasets={}
        self._aggregates={}
        self._references={}
        self._match_dates={}

    async def calculate(self,player_id:int,as_of:date|None=None,exclude_match_id:int|None=None)->dict:
        dataset_key=(as_of,exclude_match_id)
        if dataset_key not in self._datasets:
            query=select(DemoPlayerStat,DemoFile.match_date).join(DemoParseRun,DemoParseRun.id==DemoPlayerStat.parse_run_id).join(DemoFile,DemoFile.id==DemoPlayerStat.demo_file_id).where(DemoParseRun.status=="success",DemoPlayerStat.player_id.is_not(None))
            # Dates have no reliable match time, so current calculations use
            # the same conservative same-day policy as historical analytics.
            query=query.where(DemoFile.match_date < (as_of if as_of is not None else date.today()))
            if exclude_match_id is not None:
                query=query.where((DemoFile.match_id.is_(None)) | (DemoFile.match_id != exclude_match_id))
            pairs=(await self.session.execute(query)).all();loaded=defaultdict(list)
            self._match_dates[dataset_key]={row.id: match_date for row,match_date in pairs}
            for row,_ in pairs:loaded[row.player_id].append(row)
            self._datasets[dataset_key]=loaded
        grouped=self._datasets[dataset_key]
        if dataset_key not in self._aggregates:
            self._aggregates[dataset_key]={key:_aggregate(value) for key,value in grouped.items()}
        aggregates=self._aggregates[dataset_key]
        if dataset_key not in self._references:
            references=defaultdict(list)
            for aggregate in aggregates.values():
                for key in MECHANICAL_WEIGHTS|SUPPORTING_WEIGHTS:
                    if aggregate[key] is not None:references[key].append(aggregate[key])
            self._references[dataset_key]=references
        references=self._references[dataset_key]
        rows=grouped.get(player_id,[]);overall=aggregates.get(player_id) or _aggregate(rows)
        map_rel=min(1.,overall["maps"]/20);round_rel=min(1.,overall["rounds"]/400)
        mechanical_rel=sqrt(map_rel*round_rel) if overall["maps"] and overall["rounds"] else 0.
        coverage=(overall["utility_maps"]+overall["combat_maps"])/(2*overall["maps"]) if overall["maps"] else 0.
        supporting_rel=sqrt(map_rel*round_rel)*coverage
        mechanical=_block(overall,MECHANICAL_WEIGHTS,references,reliability=mechanical_rel)
        supporting=_block(overall,SUPPORTING_WEIGHTS,references,inverse={"teammates_flashed_per_flash"},reliability=supporting_rel)
        available=[(mechanical,PLAYER_STRENGTH_WEIGHTS["mechanical"]),(supporting,PLAYER_STRENGTH_WEIGHTS["supporting"])];available=[x for x in available if x[0]["score"] is not None];total=sum(w for _,w in available)
        score=sum(block["score"]*weight/total for block,weight in available) if total else None
        reliability=sum(block["reliability"]*weight/total for block,weight in available) if total else 0.
        scopes={}
        match_dates=self._match_dates.get(dataset_key,{})
        def historical_rank(row:DemoPlayerStat)->int|None:
            if as_of is None:
                return row.opponent_rank
            event_date=match_dates.get(row.id)
            if (row.opponent_rank_source != "historical_snapshot" or
                    row.opponent_rank_snapshot_date is None or event_date is None or
                    row.opponent_rank_snapshot_date > event_date):
                return None
            return row.opponent_rank
        for key,label in (("overall","overall"),("top_1_10","top_1_10"),("top_11_20","top_11_20"),("top_21_30","top_21_30"),("others","others"),("unknown","unknown")):
            selected=rows if key=="overall" else [row for row in rows if opponent_rank_group_v3(
                historical_rank(row))==key]
            metrics=_aggregate(selected);mr=sqrt(min(1,metrics["maps"]/20)*min(1,metrics["rounds"]/400)) if metrics["maps"] and metrics["rounds"] else 0
            sr=mr*((metrics["utility_maps"]+metrics["combat_maps"])/(2*metrics["maps"]) if metrics["maps"] else 0)
            scopes[label]={"mechanical":_block(metrics,MECHANICAL_WEIGHTS,references,reliability=mr),"supporting":_block(metrics,SUPPORTING_WEIGHTS,references,inverse={"teammates_flashed_per_flash"},reliability=sr),"sample":{"maps":metrics["maps"],"rounds":metrics["rounds"]}}
        final_score=None if score is None else round(score,2)
        return {"model_version":MODEL_VERSION,"as_of":as_of,
            "score":final_score,"mechanical":mechanical["score"],"supporting":supporting["score"],
            "mechanical_strength":mechanical["score"],"mechanical_reliability":mechanical["reliability"],
            "supporting_strength":supporting["score"],"supporting_reliability":supporting["reliability"],
            "player_strength":final_score,"reliability":round(reliability,4),
            "formula":PLAYER_STRENGTH_WEIGHTS,"breakdown":{"mechanical":mechanical,"supporting":supporting,"scopes":scopes,"sample":{"maps":overall["maps"],"rounds":overall["rounds"],"combat_coverage":round(overall["combat_maps"]/overall["maps"],4) if overall["maps"] else 0,"utility_coverage":round(overall["utility_maps"]/overall["maps"],4) if overall["maps"] else 0}}}

    async def calculate_and_store(self,player,as_of:date|None=None)->dict:
        result=await self.calculate(player.id,as_of)
        if as_of is None:
            player.mechanical_strength_v3=result["mechanical_strength"];player.supporting_strength_v3=result["supporting_strength"];player.player_strength_v3=result["player_strength"];player.player_strength_v3_reliability=result["reliability"];player.player_strength_v3_breakdown=result["breakdown"];player.player_strength_v3_model_version=MODEL_VERSION
        return result
