from __future__ import annotations
from dataclasses import replace
from cs2eye.analytics.matchup_config import MatchupModelConfig
from cs2eye.analytics.scoring.core import FactorInput,ScoringBreakdown,ScoringFactor,score_factors

def reliability_multiplier(mode:str,reliability:float)->float:
    reliability=max(0.,min(1.,reliability))
    if mode=="none":return 1.
    # min_reliability is the gate; a signal which passes it is retained.
    if mode=="gated":return 1.
    if mode=="linear":return reliability
    if mode=="conservative":return reliability**2
    if mode=="thresholded":return 0. if reliability<.30 else reliability*.6 if reliability<.60 else reliability
    raise ValueError(f"Unknown reliability mode: {mode}")

def calculate_matchup(inputs:list[FactorInput],legacy_reliability:float,config:MatchupModelConfig)->ScoringBreakdown:
    configured=[replace(x,weight=config.factors[x.key].weight) for x in inputs if x.key in config.factors]
    if config.overall_mode=="legacy":return replace(score_factors(configured,legacy_reliability),model_version=config.version)
    factors=[];contributions=[];coverage=0.;raw_coverage=0.
    for item in configured:
        fc=config.factors[item.key];available=item.available and item.normalized_score is not None
        score=None if not available else max(0.,min(100.,float(item.normalized_score)))
        reliability=max(0.,min(1.,float(item.confidence or 0)))
        multiplier=0. if not available or reliability<fc.min_reliability else reliability_multiplier(fc.reliability_mode,reliability)
        impact=0. if score is None else max(-fc.max_effect,min(fc.max_effect,(score-50)*fc.weight*multiplier))
        if available:raw_coverage+=fc.weight
        coverage+=fc.weight*multiplier;contributions.append(impact)
        factors.append(ScoringFactor(item.key,item.label,item.raw_value,None if score is None else round(score,2),fc.weight,round(fc.weight*multiplier,6),round(impact,2),item.sample_size,round(reliability,4),item.reason,available,item.reference_value,item.reference_source))
    raw=max(0.,min(100.,50+sum(contributions)));magnitude=sum(abs(x) for x in contributions)
    agreement=0. if not magnitude else abs(sum(contributions))/magnitude
    coverage_multiplier=config.coverage_floor+(1-config.coverage_floor)*coverage
    agreement_multiplier=config.agreement_floor+(1-config.agreement_floor)*agreement
    overall=max(0.,min(1.,coverage_multiplier*agreement_multiplier));final=50+(raw-50)*overall
    result=ScoringBreakdown(config.version,round(raw,2),round(overall,4),round(final-raw,2),round(final,2),factors)
    object.__setattr__(result,"raw_coverage",round(raw_coverage,4));object.__setattr__(result,"effective_coverage",round(coverage,4));object.__setattr__(result,"factor_agreement_score",round(agreement,4))
    return result

def inputs_from_payload(payload:dict)->list[FactorInput]:
    return [FactorInput(x["key"],x.get("label",x["key"]),None,x.get("score"),x.get("weight",0),x.get("sample"),x.get("confidence"),x.get("reason"),x.get("available",x.get("score") is not None)) for x in payload.get("factors",[])]

def apply_config_to_payload(payload:dict,config:MatchupModelConfig)->dict:
    result=calculate_matchup(inputs_from_payload(payload),float(payload.get("reliability") or 0),config)
    score=result.final_score;a=payload["team_a"]["id"];b=payload["team_b"]["id"]
    winner=a if score>53 else b if score<47 else None
    return {**payload,"model_version":config.version,"team_a":{**payload["team_a"],"score":score,"advantage":round(score-50,2)},"team_b":{**payload["team_b"],"score":round(100-score,2),"advantage":round(50-score,2)},"raw_score":result.raw_score,"reliability":result.reliability,"raw_coverage":getattr(result,"raw_coverage",None),"effective_coverage":getattr(result,"effective_coverage",None),"factor_agreement_score":getattr(result,"factor_agreement_score",None),"advantage":{**payload.get("advantage",{}),"team_id":winner},"factors":[{**x.__dict__,"score":x.normalized_score,"sample":x.sample_size} for x in result.factors]}
